import streamlit as st

st.title('Quotatore trasporti con bisarca.')

left, right = st.columns(2, vertical_alignment="bottom")
country_start = left.selectbox('Paese di partenza', ['Italia', 'Francia', 'Germania'])
address_start = left.text_input('Città, CAP o indirizzo di partenza')
country_end   = right.selectbox('Paese di destinazione', ['Italia', 'Francia', 'Germania'])
address_end   = right.text_input('Città, CAP o indirizzo di destinazione')


st.subheader('Che veicolo vuoi trasportare')
vehicle_type         = st.selectbox('Tipo di veicolo', ['Macchina', 'Roulotte', 'Motoscafo', 'Aereo'])
vehicle_manufacturer = st.selectbox('Marca', ['Audi', 'BMV'])
vehicle_model        = st.selectbox('Modello', ['A3', 'A4', 'R8'])
vehicle_number       = st.number_input('Numero di veicoli', step = 1)

st.subheader('Dettagli aggiuntivi')
is_running             = st.checkbox('Marciante')
is_remote_location     = st.checkbox('Località remota')
is_return_route_needed = st.checkbox('Prenota il ritorno')
additional_information = st.text_area('Eventuali informazioni aggiuntive per il trasportatore')

st.subheader('Date')
st.date_input('Data di partenza')

