import streamlit as st
import pandas as pd
import requests
from polyline import decode
import folium
from streamlit_folium import st_folium

df = pd.read_csv('car_db_metric_small.csv')

st.title('Quotatore trasporti con bisarca')
st.success("""
Ciao Lea, questo sarà il nostro sito demo: ci servirà per capire cosa vogliamo nell'applicazione,
quindi non badare alla grafica o al funzionamento in quanto la versione definitiva sarà tutta 
diversa.
Per ora ho solo abbozzato un algoritmo per il calcolo del percorso e del prezzo.
Non sapendo cosa ti serve potrebbe essere del tutto inutile, ma almeno ho già predisposto
un po' di cose che ci saranno utili per dopo. 
""")
st.image('bisarca1.jpg')
st.caption('Ok, non è proprio una bisarca, ma questa foto è troppo bella :)')

# ── Session state init ───────────────────────────────────────────────────────
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

# ── Predefined routes (in session_state so additions survive reruns) ─────────
_DEFAULT_ROUTES = [
    {
        "id": 1,
        "comuni_partenza": ["Torino", "Moncalieri", "Collegno"],
        "comuni_destinazione": ["Milano", "Sesto San Giovanni", "Cinisello Balsamo"],
        "prezzo_fisso": 250.0,
        "note": "Torino area → Milano area",
    },
    {
        "id": 2,
        "comuni_partenza": ["Roma", "Fiumicino", "Ciampino"],
        "comuni_destinazione": ["Napoli", "Caserta", "Salerno"],
        "prezzo_fisso": 320.0,
        "note": "Roma area → Napoli area",
    },
]

if 'predefined_routes' not in st.session_state:
    st.session_state.predefined_routes = [r.copy() for r in _DEFAULT_ROUTES]


def find_predefined_route(start_city, end_city):
    for route in st.session_state.predefined_routes:
        if (start_city in route["comuni_partenza"] and
                end_city in route["comuni_destinazione"]):
            return route["prezzo_fisso"], route["note"]
    return None, None


# ── Location data ────────────────────────────────────────────────────────────
@st.cache_data
def get_italian_postal_codes():
    url = "https://raw.githubusercontent.com/matteocontrini/comuni-json/master/comuni.json"
    response = requests.get(url)
    data = response.json()
    locations = []
    for comune in data:
        if isinstance(comune.get('cap'), list):
            for cap in comune.get('cap', ['N/A']):
                city = comune.get('nome', '')
                prov = comune.get('sigla', '')
                locations.append({'display': f"{city} ({cap}) - {prov}",
                                  'city': city, 'postal_code': cap, 'province': prov})
        else:
            cap  = comune.get('cap', 'N/A')
            city = comune.get('nome', '')
            prov = comune.get('sigla', '')
            locations.append({'display': f"{city} ({cap}) - {prov}",
                              'city': city, 'postal_code': cap, 'province': prov})
    return locations


locations        = get_italian_postal_codes()
location_options = [loc['display'] for loc in locations]
all_cities       = sorted(set(loc['city'] for loc in locations))


# ── Helpers ──────────────────────────────────────────────────────────────────
def geocode_location(postal_code, city, country="Italy"):
    url    = "https://api.openrouteservice.org/geocode/search"
    params = {
        "api_key": st.secrets["ORS_API_KEY"],
        "text": f"{postal_code} {city}, {country}",
        "boundary.country": "IT",
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['features']:
            coords = data['features'][0]['geometry']['coordinates']
            return coords[1], coords[0]
    return None, None


def get_route_details(start_coords, end_coords):
    url     = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {'Authorization': st.secrets["ORS_API_KEY"], 'Content-Type': 'application/json'}
    body    = {
        "coordinates": [[start_coords[1], start_coords[0]],
                        [end_coords[1],   end_coords[0]]],
        "extra_info": ["tollways"],
        "units": "km",
    }
    response = requests.post(url, json=body, headers=headers)
    return response.json() if response.status_code == 200 else None


def estimate_toll_cost(distance_km):
    return distance_km * 0.8 * 0.24  # Class 5, ~80% highway


def calculate_pricing(distance_km, duration_hours, fixed_price=None, fixed_note=None):
    fuel_cost   = distance_km / 4 * 1.70
    toll_cost   = estimate_toll_cost(distance_km)
    driver_cost = duration_hours * 25
    subtotal    = fuel_cost + toll_cost + driver_cost
    markup      = subtotal * 0.20
    calc_total  = subtotal + markup

    return {
        "distance_km":      distance_km,
        "duration_hours":   duration_hours,
        "fuel_cost":        fuel_cost,
        "toll_cost":        toll_cost,
        "driver_cost":      driver_cost,
        "subtotal":         subtotal,
        "markup":           markup,
        "calculated_total": calc_total,
        "total":            fixed_price if fixed_price is not None else calc_total,
        "is_fixed":         fixed_price is not None,
        "fixed_note":       fixed_note,
    }


def create_route_map(start_coords, end_coords, route_geometry):
    center = ((start_coords[0] + end_coords[0]) / 2,
              (start_coords[1] + end_coords[1]) / 2)
    m = folium.Map(location=center, zoom_start=8)
    folium.Marker(start_coords, popup="Start",
                  icon=folium.Icon(color='green', icon='play')).add_to(m)
    folium.Marker(end_coords, popup="Destination",
                  icon=folium.Icon(color='red', icon='stop')).add_to(m)
    if route_geometry:
        folium.PolyLine(route_geometry, color='blue', weight=4).add_to(m)
    return m


# ── Two-tab layout ───────────────────────────────────────────────────────────
tab_app, tab_tratte = st.tabs(["🚚 Quotatore", "⚙️ Tratte standard"])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Quotatore
# ════════════════════════════════════════════════════════════════════════════
with tab_app:
    left, right = st.columns(2, vertical_alignment="bottom")

    country_start = left.selectbox('Paese di partenza', ['Italia', 'Francia'],
                                   key='country_start')
    if country_start == 'Francia':
        st.info('Hey :) niente Francia per ora.')

    st.info("""Per ora, per cercare il comune, lo devi scrivere con la prima lettera maiuscola, altrimenti
puoi cercare per CAP. Ovviamente nella versione definitiva daremo anche la possibilità
di inserire degli indirizzi completi e funzionerà tutto meglio.""")

    address_start = left.selectbox('Città e CAP di partenza',
                                   options=[""] + location_options,
                                   index=0, key='address_start')

    country_end = right.selectbox('Paese di destinazione', ['Italia', 'Francia'],
                                  key='country_end')
    if country_end == 'Francia':
        st.info('Hey :) niente Francia per ora.')
    address_end = right.selectbox('Città e CAP di destinazione',
                                  options=[""] + location_options,
                                  index=0, key='address_end')

    st.subheader('Che veicolo vuoi trasportare')
    vehicle_type = st.selectbox('Tipo di veicolo',
                                ['Macchina', 'Roulotte', 'Astronave Aliena'],
                                index=0, key='vehicle_type')
    if vehicle_type == 'Roulotte':
        st.info('Per ora non ho ancora trovato un database con informazioni sulle roulotte')

    manufacturers        = sorted(df['make'].unique())
    vehicle_manufacturer = st.selectbox("Costruttore:", [""] + list(manufacturers),
                                        index=0, key='vehicle_manufacturer')

    selected_car = None
    if vehicle_manufacturer:
        df_filtered   = df[df['make'] == vehicle_manufacturer]
        models        = sorted(df_filtered['model'].unique())
        vehicle_model = st.selectbox("Modello:", [""] + list(models),
                                     index=0, key='vehicle_model')
        if vehicle_model:
            selected_car = df_filtered[df_filtered['model'] == vehicle_model].iloc[0]

    if st.button("Calcola il percorso", type="primary"):
        if not (country_start and country_end and address_start and address_end):
            st.warning("Compilare tutti i campi dei paesi e degli indirizzi.")
            st.session_state.route_calculated = False
        else:
            with st.spinner("Calcolo il percorso..."):
                start_postal = address_start.split('-')[0].split('(')[1].replace(')', '')
                start_city   = address_start.split('-')[0].split('(')[0].strip()
                end_postal   = address_end.split('-')[0].split('(')[1].replace(')', '')
                end_city     = address_end.split('-')[0].split('(')[0].strip()

                fixed_price, fixed_note = find_predefined_route(start_city, end_city)

                start_coords = geocode_location(start_postal, start_city)
                end_coords   = geocode_location(end_postal, end_city)

                if not (start_coords[0] and end_coords[0]):
                    st.error("Impossibile trovare le coordinate per la mappa.")
                    st.session_state.route_calculated = False
                else:
                    route_data = get_route_details(start_coords, end_coords)

                    if not route_data or 'routes' not in route_data or not route_data['routes']:
                        st.error("Impossibile calcolare il percorso.")
                        st.session_state.route_calculated = False
                    else:
                        route_info     = route_data['routes'][0]
                        summary        = route_info['summary']
                        distance_km    = summary['distance']
                        duration_hours = summary['duration'] / 3600

                        route_geometry = []
                        if 'geometry' in route_info:
                            geometry = route_info['geometry']
                            if isinstance(geometry, str):
                                route_geometry = decode(geometry)
                            elif isinstance(geometry, dict) and 'coordinates' in geometry:
                                route_geometry = geometry['coordinates']

                        pricing = calculate_pricing(distance_km, duration_hours,
                                                    fixed_price=fixed_price,
                                                    fixed_note=fixed_note)

                        st.session_state.route_calculated = True
                        st.session_state.pricing          = pricing
                        st.session_state.route_geometry   = route_geometry
                        st.session_state.start_coords     = start_coords
                        st.session_state.end_coords       = end_coords
                        st.success("Percorso calcolato!")

    # Results
    if st.session_state.route_calculated and st.session_state.pricing:
        pricing = st.session_state.pricing

        # if pricing.get("is_fixed"):
        #     st.info(f"💡 Tratta standard rilevata: **{pricing['fixed_note']}** — prezzo fisso applicato.")

        col1, col2, col3 = st.columns(3)
        col1.metric("Distanza",      f"{pricing['distance_km']:.1f} km")
        col2.metric("Durata",        f"{pricing['duration_hours']:.1f} h")
        col3.metric("Prezzo Totale", f"€ {pricing['total']:.2f}")

        st.subheader("Struttura dei costi")
        st.info("""
        Per evitare di fare del lavoro senza sapere cosa ti serve, qui ho 
    solo abbozzato alcune variabili che potrebbero influire sul costo
    del trasporto. Il cliente vedrà solo il totale, cioè la somma di tutti 
    i costi e il tuo margine di guadagno (markup), che qui ho messo fisso al 
    20%.
        """)

        rows = [
            {"Item": "Carburante (stimato)", "Ammontare (€)": f"{pricing['fuel_cost']:.2f}"},
            {"Item": "Autostrada (stimata)", "Ammontare (€)": f"{pricing['toll_cost']:.2f}"},
            {"Item": "Guidatore (stimato)",  "Ammontare (€)": f"{pricing['driver_cost']:.2f}"},
            {"Item": "Markup (20%)",         "Ammontare (€)": f"{pricing['markup']:.2f}"},
        ]
        if pricing.get("is_fixed"):
            rows.append({"Item": "Totale algoritmo",            "Ammontare (€)": f"{pricing['calculated_total']:.2f}"})
            rows.append({"Item": "Prezzo fisso (tratta stdandard)", "Ammontare (€)": f"{pricing['total']:.2f}"})
        else:
            rows.append({"Item": "TOTALE", "Ammontare (€)": f"{pricing['total']:.2f}"})

        st.table(pd.DataFrame(rows))

        st.subheader("Percorso")
        route_map = create_route_map(st.session_state.start_coords,
                                     st.session_state.end_coords,
                                     st.session_state.route_geometry)
        st_folium(route_map, width=700, height=500)

    with st.expander('Campi che non ho ancora incluso nei calcoli'):
        st.caption('Da qui in poi nulla funziona, serve solo a me per ricordarmi le prossime cose da fare.')
        st.number_input('Numero di veicoli', step=1)
        st.subheader('Dettagli aggiuntivi')
        st.checkbox('Non marciante')
        st.checkbox('Località remota')
        st.text_area('Eventuali informazioni aggiuntive per il trasportatore')
        st.subheader('Date')
        st.checkbox('Prenota il ritorno')
        st.date_input('Data di partenza')


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Gestione tratte standard
# ════════════════════════════════════════════════════════════════════════════
with tab_tratte:

    st.subheader("Tratte standard a prezzo fisso")
    st.info("""
    Ho pensato che potrebbe esserti utile una pagina dove impostare delle tratte
    con prezzo standard. Per ora è una versione semplice, quindi imposti solo i comuni di
    partenza, di arrivo e il prezzo. Un cliente che richiede un trasporta da e verso questi
    comuni, riceverà il prezzo standard.
    """)
    st.warning("""
    Attenzione: per ora tutte le tratte standard che aggiungi oltre a quelle di esempio 
    fornite da me verranno cancellate ogni volta che chiudi la pagina web. 
    """)
    # ── Tabella tratte esistenti ──────────────────────────────────────────
    routes_display = [
        {
            "Comuni di partenza": ", ".join(r["comuni_partenza"]),
            "Comuni di destinazione": ", ".join(r["comuni_destinazione"]),
            "Prezzo fisso (€)": f"€ {r['prezzo_fisso']:.2f}",
            "Descrizione": r["note"],
        }
        for r in st.session_state.predefined_routes
    ]

    st.dataframe(pd.DataFrame(routes_display), use_container_width=True, hide_index=True)

    st.divider()

    # ── Form aggiunta nuova tratta ────────────────────────────────────────
    st.subheader("Aggiungi nuova tratta")

    col_a, col_b = st.columns(2)
    with col_a:
        new_comuni_start = st.multiselect(
            "Comuni di partenza",
            options=all_cities,
            placeholder="Cerca comune...",
            key="new_route_start",
        )
    with col_b:
        new_comuni_end = st.multiselect(
            "Comuni di destinazione",
            options=all_cities,
            placeholder="Cerca comune...",
            key="new_route_end",
        )

    col_c, col_d = st.columns([1, 2])
    with col_c:
        new_price = st.number_input(
            "Prezzo fisso (€)", min_value=0.0, step=10.0, format="%.2f",
            key="new_route_price",
        )
    with col_d:
        new_note = st.text_input(
            "Descrizione (opzionale)",
            placeholder="Es. Torino area → Roma area",
            key="new_route_note",
        )

    if st.button("➕ Aggiungi tratta", type="primary"):
        if not new_comuni_start or not new_comuni_end:
            st.warning("Seleziona almeno un comune di partenza e uno di destinazione.")
        elif new_price <= 0:
            st.warning("Inserisci un prezzo valido maggiore di zero.")
        else:
            note = new_note.strip() if new_note.strip() else \
                f"{', '.join(new_comuni_start[:2])} → {', '.join(new_comuni_end[:2])}"
            new_route = {
                "id": len(st.session_state.predefined_routes) + 1,
                "comuni_partenza": list(new_comuni_start),
                "comuni_destinazione": list(new_comuni_end),
                "prezzo_fisso": float(new_price),
                "note": note,
            }
            st.session_state.predefined_routes.append(new_route)
            st.success(f"Tratta aggiunta: **{note}** — € {new_price:.2f}")
            st.rerun()