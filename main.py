import streamlit as st
import pandas as pd
import requests
from polyline import decode
import folium
from streamlit_folium import st_folium

df = (pd.read_csv('car_db_metric_small.csv'))

st.title('Quotatore trasporti con bisarca')
st.success("""
Ciao Lea, questo sarà il nostro sito demo. 
Per ora ho solo creato un abbozzo di algoritmo per il calcolo del percorso e del prezzo.
Non sapendo cosa ti serve potrebbe essere del tutto inutile, ma almeno ho già predisposto
un po' di cose che ci saranno utili per dopo. 
""")
st.image('bisarca1.jpg')
st.caption('Ok, non è proprio una bisarca, ma questa foto è troppo bella :)')

# Initialize session state
if 'route_calculated' not in st.session_state:
    st.session_state.route_calculated = False
if 'pricing' not in st.session_state:
    st.session_state.pricing = None
if 'route_geometry' not in st.session_state:
    st.session_state.route_geometry = None
if 'start_coords' not in st.session_state:
    st.session_state.start_coords = None
if 'end_coords' not in st.session_state:
    st.session_state.end_coords = None

@st.cache_data
def get_italian_postal_codes():
    url = "https://raw.githubusercontent.com/matteocontrini/comuni-json/master/comuni.json"
    response = requests.get(url)
    data = response.json()

    locations = []
    for comune in data:
        if isinstance(comune.get('cap'), list):
            for i in range(len(comune.get('cap'))):
                cap = comune.get('cap', ['N/A'])[i]
                city = comune.get('nome', '')
                prov = comune.get('sigla', '')
                locations.append({
                    'display': f"{city} ({cap}) - {prov}",
                    'city': city,
                    'postal_code': cap,
                    'province': prov
                })
        else:
            cap = comune.get('cap', 'N/A')
            city = comune.get('nome', '')
            prov = comune.get('sigla', '')
            locations.append({
                'display': f"{city} ({cap}) - {prov}",
                'city': city,
                'postal_code': cap,
                'province': prov
            })

    return locations

locations = get_italian_postal_codes()
location_options = [loc['display'] for loc in locations]


left, right = st.columns(2, vertical_alignment="bottom")
country_start = left.selectbox('Paese di partenza', ['Italia', 'Francia'])
if country_start == 'Francia':
    st.info('Hey :) niente Francia per ora.')
address_start = left.selectbox('Città e CAP di partenza',
                               options=[""] + location_options,
                               index=0)

country_end   = right.selectbox('Paese di destinazione', ['Italia', 'Francia'])
if country_end == 'Francia':
    st.info('Hey :) niente Francia per ora.')
address_end   = right.selectbox('Città e CAP di destinazione',
                                options=[""] + location_options,
                                index=0)


st.subheader('Che veicolo vuoi trasportare')
vehicle_type = st.selectbox('Tipo di veicolo', ['Macchina', 'Roulotte', 'Astronave Aliena'], index = 0)
if vehicle_type == 'Astronave Aliena':
    st.info('Sarebbe figo eh?!')
if vehicle_type == 'Roulotte':
    st.info('Per ora non ho ancora trovato un database con informazioni sulle roulotte')

manufacturers = sorted(df['make'].unique())
vehicle_manufacturer = st.selectbox(
    "Costruttore:",
    [""] + list(manufacturers),
    index=0
)

selected_car = None
if vehicle_manufacturer:
    df_filtered = df[df['make'] == vehicle_manufacturer]
    models = sorted(df_filtered['model'].unique())

    vehicle_model = st.selectbox(
        "Modello:",
        [""] + list(models),
        index=0
    )

    if vehicle_model:
        selected_cars = df_filtered[df_filtered['model'] == vehicle_model]
        selected_car  = selected_cars.iloc[0]

def geocode_location(postal_code, city, country="Italy"):
    """Convert postal code + city to coordinates using OpenRouteService"""
    url = "https://api.openrouteservice.org/geocode/search"
    params = {
        "api_key": st.secrets["ORS_API_KEY"],
        "text": f"{postal_code} {city}, {country}",
        "boundary.country": "IT"
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['features']:
            coords = data['features'][0]['geometry']['coordinates']
            return coords[1], coords[0]  # lat, lon
    return None, None

def get_route_details(start_coords, end_coords):
    """Get route details including distance, time, and geometry"""
    url = "https://api.openrouteservice.org/v2/directions/driving-car"

    headers = {
        'Authorization': st.secrets["ORS_API_KEY"],
        'Content-Type': 'application/json'
    }

    body = {
        "coordinates": [
            [start_coords[1], start_coords[0]],  # lon, lat
            [end_coords[1], end_coords[0]]
        ],
        "extra_info": ["tollways"],
        "units": "km"
    }

    response = requests.post(url, json=body, headers=headers)

    if response.status_code == 200:
        return response.json()
    return None

def estimate_toll_cost(distance_km):
    """
    Estimate Italian highway toll costs
    Based on average Italian toll rates: ~0.07 €/km for cars
    """
    base_rates = {
        "Class A (Car/Motorcycle)": 0.07,
        "Class B (Car w/ trailer)": 0.10,
        "Class 3": 0.14,
        "Class 4": 0.18,
        "Class 5": 0.24
    }

    rate = base_rates.get("Class 5", 0.24)

    # Assume 80% of route is on highways (conservative estimate)
    highway_distance = distance_km * 0.8

    return highway_distance * rate

def calculate_pricing(distance_km, duration_hours):
    fuel_price       = 1.70
    fuel_consumption = 4 # L/km
    hourly_rate      = 25 # Driver Hourly Rate (€/h)
    markup_percent   = 20
    # fuel_cost = (distance_km / 100) * fuel_consumption * fuel_price
    print(distance_km, fuel_consumption, fuel_price)
    fuel_cost = (distance_km) / fuel_consumption * fuel_price

    toll_cost = estimate_toll_cost(distance_km)

    driver_cost = duration_hours * hourly_rate

    subtotal = fuel_cost + toll_cost + driver_cost

    markup = subtotal * (markup_percent / 100)

    total = subtotal + markup

    return {
        "distance_km": distance_km,
        "duration_hours": duration_hours,
        "fuel_cost": fuel_cost,
        "toll_cost": toll_cost,
        "driver_cost": driver_cost,
        "subtotal": subtotal,
        "markup": markup,
        "total": total
    }



def create_route_map(start_coords, end_coords, route_geometry):
    """Create a folium map with the route"""
    # Create map centered on midpoint
    center_lat = (start_coords[0] + end_coords[0]) / 2
    center_lon = (start_coords[1] + end_coords[1]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

    # Add markers
    folium.Marker(
        start_coords,
        popup="Start",
        icon=folium.Icon(color='green', icon='play')
    ).add_to(m)

    folium.Marker(
        end_coords,
        popup="Destination",
        icon=folium.Icon(color='red', icon='stop')
    ).add_to(m)

    # Add route line
    if route_geometry:
        # Decode the geometry (it's in [lon, lat] format)
        route_coords = [[coord[1], coord[0]] for coord in route_geometry]
        folium.PolyLine(
            route_coords,
            color='blue',
            weight=4,
            opacity=0.7
        ).add_to(m)

    return m

if st.button("Calcola il percorso", type="primary"):
    if not (country_start and country_end and address_start and address_end):
        st.warning("Compilare tutti i campi dei paesi e degli esercizi.")
        st.session_state.route_calculated = False
    else:
        with st.spinner("Calcolo il percorso..."):
            start_postal = address_start.split('-')[0].split('(')[1].replace(')', '')
            start_city   = address_start.split('-')[0].split('(')[0].strip()
            end_postal = address_end.split('-')[0].split('(')[1].replace(')', '')
            end_city   = address_end.split('-')[0].split('(')[0].strip()

            # Geocode locations
            start_coords = geocode_location(start_postal, start_city)
            end_coords = geocode_location(end_postal, end_city)

            if not (start_coords[0] and end_coords[0]):
                st.error("Impossibile trovare le coordinate per la mappa, Tommy ha probabilmente fatto casino.")
                st.session_state.route_calculated = False
            else:
                # Get route details
                route_data = get_route_details(start_coords, end_coords)

                if not route_data:
                    st.error("Impossibile calcolare percorso, Tommy ha fatto casino o alcuni dati non sono compilati.")
                    st.session_state.route_calculated = False
                else:
                    # Parse route data
                    if isinstance(route_data, str):
                        import json
                        route_data = json.loads(route_data)

                    if 'routes' not in route_data or len(route_data['routes']) == 0:
                        st.error("Nessun percorso trovato.")
                        st.session_state.route_calculated = False
                    else:
                        route_info = route_data['routes'][0]
                        summary = route_info['summary']
                        print(summary)

                        distance_km = summary['distance']
                        duration_hours = summary['duration'] / 3600

                        # Safe geometry extraction
                        route_geometry = []
                        if 'geometry' in route_info:
                            geometry = route_info['geometry']
                            if isinstance(geometry, str):
                                route_geometry = decode(geometry)
                            elif isinstance(geometry, dict) and 'coordinates' in geometry:
                                route_geometry = geometry['coordinates']

                        # Calculate pricing


                        pricing = calculate_pricing(
                            distance_km, duration_hours)

                        # Store in session state
                        st.session_state.route_calculated = True
                        st.session_state.pricing = pricing
                        st.session_state.route_geometry = route_geometry
                        st.session_state.start_coords = start_coords
                        st.session_state.end_coords = end_coords

                        st.success("Percorso calcolato!")

# Display results if route is calculated
if st.session_state.route_calculated and st.session_state.pricing:
    pricing = st.session_state.pricing

    # Route summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Distanza", f"{pricing['distance_km']:.1f} km")
    with col2:
        st.metric("Durata", f"{pricing['duration_hours']:.1f} h")
    with col3:
        st.metric("**Prezzo Totale**", f"€{pricing['total']:.2f}")

    st.subheader("Struttura dei costi, in questa demo.")

    breakdown_df = pd.DataFrame([
        {"Item": "Carburante", "Ammontare (€)": f"{pricing['fuel_cost']:.2f}"},
        {"Item": "Autostrada (stimata)", "Ammontare (€)": f"{pricing['toll_cost']:.2f}"},
        {"Item": "Guidatore", "Ammontare (€)": f"{pricing['driver_cost']:.2f}"},
        {"Item": f"Markup (20%)", "Ammontare (€)": f"{pricing['markup']:.2f}"},
        {"Item": "**TOTAL**", "Ammontare (€)": f"**€{pricing['total']:.2f}**"},
    ])

    st.table(breakdown_df)

    # Map visualization
    st.subheader("Percorso")

    route_map = create_route_map(
        st.session_state.start_coords,
        st.session_state.end_coords,
        st.session_state.route_geometry
    )

    st_folium(route_map, width=700, height=500)


with st.expander('Parti che non funzionano ancora'):
    st.caption('Da qui in poi nulla funziona, serve solo a me per ricordarmi le prossime cose da fare.')
    vehicle_number       = st.number_input('Numero di veicoli', step = 1)

    st.subheader('Dettagli aggiuntivi')
    is_not_running             = st.checkbox('Non marciante')
    is_remote_location     = st.checkbox('Località remota')
    additional_information = st.text_area('Eventuali informazioni aggiuntive per il trasportatore')

    st.subheader('Date')
    is_return_route_needed = st.checkbox('Prenota il ritorno')
    st.date_input('Data di partenza')