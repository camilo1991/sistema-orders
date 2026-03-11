import streamlit as st
import requests
import pandas as pd
import urllib3
from datetime import datetime, timedelta
from io import BytesIO

# Configuración de Seguridad y Página
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="Audifarma Report Manager", page_icon="📦", layout="wide")

# Estilo para mejorar la visualización en la web
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] { background-color: #ffffff; border: 1px solid #ddd; padding: 10px; border-radius: 5px; }
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
        f"searchCriteria[pageSize]=1500"
    )
    response = requests.get(f"{BASE_URL}/orders{params}", headers=headers, verify=False, timeout=25)
    response.raise_for_status()
    return response.json().get('items', [])

# --- INTERFAZ DE USUARIO (SIDEBAR) ---
st.sidebar.title("🔐 Acceso Seguro")
user = st.sidebar.text_input("Usuario Magento", value="")
password = st.sidebar.text_input("Contraseña", value="", type="password")

st.sidebar.divider()
st.sidebar.title("📅 Rango de Fechas")
d_inicio = st.sidebar.date_input("Desde", datetime.now())
d_fin = st.sidebar.date_input("Hasta", datetime.now())

# Ajuste de zona horaria UTC (Bogotá UTC-5)
dt_inicio_utc = (datetime.combine(d_inicio, datetime.min.time()) + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
dt_fin_utc = (datetime.combine(d_fin, datetime.max.time()) + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

btn_consultar = st.sidebar.button("🚀 Generar Reporte", use_container_width=True)

# --- CUERPO PRINCIPAL ---
st.title("📦 Sistema de Órdenes Audifarma")
st.info("Ingresa tus credenciales y selecciona las fechas para extraer el reporte detallado.")

if btn_consultar:
    if not user or not password:
        st.warning("⚠️ Se requieren credenciales para acceder a la API de Magento.")
    else:
        with st.spinner("Conectando con el servidor..."):
            token = obtener_token(user, password)
            if not token:
                st.error("❌ Error de autenticación. Verifica tus datos de acceso.")
            else:
                try:
                    orders = fetch_magento_data(token, dt_inicio_utc, dt_fin_utc)
                    if not orders:
                        st.info("No se encontraron órdenes para este periodo.")
                    else:
                        reporte = []
                        for o in orders:
                            # Ajuste de fecha para visualización local
                            dt_local = datetime.strptime(o['created_at'], '%Y-%m-%d %H:%M:%S') - timedelta(hours=5)
                            
                            billing = o.get('billing_address', {})
                            direccion = billing.get('street', [''])[0] if billing.get('street') else ''
                            
                            base = {
                                "Id": o['increment_id'],
                                "Fecha Compra": dt_local.strftime('%Y-%m-%d'),
                                "Nombre del cliente": f"{o.get('customer_firstname', '')} {o.get('customer_lastname', '')}",
                                "Ciudad": billing.get('city'),
                                "Departamento": billing.get('region'),
                                "Dirección": direccion,
                                "Correo electrónico": o.get('customer_email'),
                                "Teléfono": billing.get('telephone'),
                                "Valor del domicilio": float(o.get('shipping_amount', 0)),
                                "Valor total de la compra": float(o.get('grand_total', 0)),
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
                        
                        # Orden oficial de las 14+ columnas
                        cols_finales = [
                            "Id", "Fecha Compra", "Nombre del cliente", "Ciudad", "Departamento", 
                            "Dirección", "Correo electrónico", "Teléfono", "SKU", 
                            "Nombre del producto", "Cantidad comprada", "Precio Unitario", 
                            "Subtotal Producto", "Valor del domicilio", 
                            "Valor total de la compra", "Estado de la compra"
                        ]
                        df = df[cols_finales]

                        # Métricas rápidas
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Órdenes Únicas", df['Id'].nunique())
                        c2.metric("Total Productos", int(df['Cantidad comprada'].sum()))
                        c3.metric("Venta Total", f"${df['Valor total de la compra'].unique().sum():,.0f}")

                        st.divider()
                        st.dataframe(df, use_container_width=True)

                        # --- LÓGICA DE DESCARGA EXCEL (CORREGIDA) ---
                        output = BytesIO()
                        # Es vital usar xlsxwriter para que el formato sea nativo de Excel
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            df.to_excel(writer, index=False, sheet_name='Reporte_Magento')
                        
                        processed_data = output.getvalue()

                        st.download_button(
                            label="📥 Descargar Reporte en Excel (.xlsx)",
                            data=processed_data,
                            file_name=f"Reporte_Magento_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"Error en el procesamiento: {e}")