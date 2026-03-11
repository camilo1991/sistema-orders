import streamlit as st
import requests
import pandas as pd
import urllib3
from datetime import datetime, timedelta
from io import BytesIO

# Configuración de Seguridad y Página
urllib3.disable_warnings(urllib3.exceptions.Insecure_requestWarning)
st.set_page_config(page_title="Magento Report Manager Pro", page_icon="📦", layout="wide")

# --- BLOQUE DE DISEÑO PARA MODO OSCURO ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { color: #1f1f1f !important; font-weight: bold !important; }
    [data-testid="stMetricLabel"] { color: #555555 !important; }
    [data-testid="stMetric"] {
        background-color: #f0f2f6 !important;
        padding: 15px !important;
        border-radius: 10px !important;
        border: 1px solid #d1d1d1 !important;
    }
    </style>
    """, unsafe_allow_html=True)

BASE_URL = "https://www.audifarmadroguerias.com/rest/V1"

# --- FUNCIONES TÉCNICAS ---
def obtener_token(usuario, clave):
    auth_url = f"{BASE_URL}/integration/admin/token"
    payload = {"username": usuario, "password": clave}
    try:
        response = requests.post(auth_url, json=payload, verify=False, timeout=10)
        response.raise_for_status()
        return response.json()
    except:
        return None

def fetch_magento_data(token, f_inicio, f_fin):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = (
        f"?searchCriteria[filter_groups][0][filters][0][field]=created_at&"
        f"searchCriteria[filter_groups][0][filters][0][value]={f_inicio}&"
        f"searchCriteria[filter_groups][0][filters][0][condition_type]=gteq&"
        f"searchCriteria[filter_groups][1][filters][0][field]=created_at&"
        f"searchCriteria[filter_groups][1][filters][0][value]={f_fin}&"
        f"searchCriteria[filter_groups][1][filters][0][condition_type]=lteq&"
        f"searchCriteria[pageSize]=1000"
    )
    response = requests.get(f"{BASE_URL}/orders{params}", headers=headers, verify=False, timeout=20)
    response.raise_for_status()
    return response.json().get('items', [])

# --- INTERFAZ (SIDEBAR) CON SECRETS ---
st.sidebar.title("🔐 Acceso Magento")

# Intentar obtener credenciales desde Streamlit Secrets
user_secret = st.secrets.get("USUARIO_MAGENTO", "andrey.pena")
pass_secret = st.secrets.get("CLAVE_MAGENTO", "")

user = st.sidebar.text_input("Usuario", value=user_secret)
password = st.sidebar.text_input("Contraseña", value=pass_secret, type="password")

st.sidebar.divider()
st.sidebar.title("📅 Filtros de Fecha (Local)")
col_f1, col_f2 = st.sidebar.columns(2)
d_inicio = col_f1.date_input("Inicio", datetime.now())
h_inicio = col_f1.time_input("Hora Ini", datetime.time(datetime(2024,1,1,0,0,0)))

d_fin = col_f2.date_input("Fin", datetime.now())
h_fin = col_f2.time_input("Hora Fin", datetime.time(datetime(2024,1,1,23,59,59)))

# Ajuste de zona horaria UTC (Bogotá UTC-5)
dt_inicio_local = datetime.combine(d_inicio, h_inicio)
dt_fin_local = datetime.combine(d_fin, h_fin)
fecha_inicio_utc = (dt_inicio_local + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
fecha_fin_utc = (dt_fin_local + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

btn_consultar = st.sidebar.button("🚀 Ejecutar Reporte", use_container_width=True)

st.title("📦 Reporte de Órdenes Audifarma")

if btn_consultar:
    if not user or not password:
        st.error("Por favor, ingresa las credenciales.")
    else:
        with st.spinner("Conectando con Magento..."):
            token = obtener_token(user, password)
            if not token:
                st.error("Error de autenticación. Verifica usuario/clave.")
            else:
                try:
                    orders = fetch_magento_data(token, fecha_inicio_utc, fecha_fin_utc)
                    if not orders:
                        st.warning("No se encontraron órdenes en este rango.")
                    else:
                        reporte = []
                        for o in orders:
                            dt_utc = datetime.strptime(o['created_at'], '%Y-%m-%d %H:%M:%S')
                            dt_local = dt_utc - timedelta(hours=5)
                            
                            billing = o.get('billing_address', {})
                            direccion = billing.get('street', [''])[0] if billing.get('street') else ''
                            
                            # Datos base de la orden
                            base = {
                                "Id": o['increment_id'],
                                "Fecha Compra": dt_local.strftime('%Y-%m-%d'),
                                "Nombre del cliente": f"{o.get('customer_firstname', '')} {o.get('customer_lastname', '')}",
                                "Ciudad": billing.get('city'),
                                "Departamento": billing.get('region'),
                                "Dirección": direccion,
                                "Correo electrónico": o.get('customer_email'),
                                "Teléfono": billing.get('telephone'),
                                "Valor del domicilio": o.get('shipping_amount'),
                                "Valor total de la compra": o.get('grand_total'),
                                "Estado de la compra": o.get('status')
                            }

                            for item in o['items']:
                                if item.get('product_type') == 'simple' or 'parent_item' not in item:
                                    fila = base.copy()
                                    p_unitario = float(item.get('price', 0))
                                    cantidad = float(item.get('qty_ordered', 0))
                                    
                                    fila.update({
                                        "SKU": item['sku'],
                                        "Nombre del producto": item['name'],
                                        "Cantidad comprada": cantidad,
                                        "Precio Unitario": p_unitario,
                                        "Subtotal Producto": cantidad * p_unitario
                                    })
                                    reporte.append(fila)

                        df = pd.DataFrame(reporte)

                        # Orden exacto de columnas solicitado
                        columnas_finales = [
                            "Id", "Fecha Compra", "Nombre del cliente", "Ciudad", "Departamento", 
                            "Dirección", "Correo electrónico", "Teléfono", "SKU", 
                            "Nombre del producto", "Cantidad comprada", "Precio Unitario", 
                            "Subtotal Producto", "Valor del domicilio", 
                            "Valor total de la compra", "Estado de la compra"
                        ]
                        df = df[columnas_finales]

                        # --- MÉTRICAS ---
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Órdenes", df['Id'].nunique())
                        m2.metric("Total Items", int(df['Cantidad comprada'].sum()))
                        m3.metric("Recaudo Total", f"${df['Valor total de la compra'].unique().astype(float).sum():,.0f}")
                        m4.metric("Total Domicilios", f"${df['Valor del domicilio'].unique().astype(float).sum():,.0f}")

                        st.divider()
                        st.dataframe(df, use_container_width=True)

                        # Preparar descarga Excel
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            df.to_excel(writer, index=False, sheet_name='Reporte Magento')
                        
                        st.download_button(
                            label="📥 Descargar Reporte Excel Completo",
                            data=output.getvalue(),
                            file_name=f"Reporte_Audifarma_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                except Exception as e:
                    st.error(f"Error procesando datos: {e}")
else:
    st.info("Configura los filtros y presiona 'Ejecutar Reporte'.")