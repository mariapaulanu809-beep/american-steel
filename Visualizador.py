# -*- coding: utf-8 -*-
"""
AMERICAN STEEL COMPANY - Interfaz gráfica con Streamlit
=======================================================
Muestra, en el navegador, el procedimiento del método simplex:
modelo, matrices (tabla) iteración por iteración, solución y costos.

Requiere tener en la MISMA carpeta el archivo Algoritmo.py

Ejecutar:
    python3 -m streamlit run Visualizador.py
"""

import contextlib
import io

import numpy as np
import pandas as pd
import streamlit as st

import Algoritmo as asx

COSTO_SOLVER_EXCEL = 392416.67   # resultado de Solver en Moncada_tablas_pro.xlsx

# Los números de las celdas con fondo claro se ven en rojo oscuro para que se lean
# tanto en el tema oscuro como en el claro de Streamlit.
ROJO = "color:#c62828"


# =============================================================================
# 1. FUNCIONES DE DATOS (no dependen de Streamlit)
# =============================================================================
def resolver_modelo():
    """Arma el modelo, corre el simplex de dos fases y devuelve todo lo necesario."""
    A, b, sentidos = asx.construir_modelo()
    sim = asx.Simplex(A, b, sentidos, asx.COSTOS)
    res = sim.resolver(verbose=False)
    return dict(A=A, b=b, sentidos=sentidos, sim=sim, res=res)


def df_modelo(A, b, sentidos):
    """Matriz del modelo [A | sentido | b] con una fila final de costos."""
    filas = [f"({r[0]}) {r[1]}" for r in asx.RESTRICCIONES]
    df = pd.DataFrame(A, index=filas, columns=asx.NOMBRES)
    df["Sentido"] = sentidos
    df["b"] = b
    return df


def estilo_modelo(df):
    """Resalta en color los coeficientes distintos de cero."""
    def f(d):
        css = pd.DataFrame("", index=d.index, columns=d.columns)
        num = d[asx.NOMBRES].astype(float)
        css[asx.NOMBRES] = np.where(num.values != 0,
                                    f"background-color:#e3f2fd;{ROJO};font-weight:bold", "")
        css["b"] = f"background-color:#fff8e1;{ROJO};font-weight:bold"
        return css
    fmts = {c: asx.fmt for c in asx.NOMBRES + ["b"]}
    return df.style.apply(f, axis=None).format(fmts)


def estilo_tabla (df, entra=None):
    """
    Resalta el pivote del tabla:
      - amarillo: columna de la variable que entró
      - azul:     fila de la variable que entró (fila pivote)
      - naranja:  celda pivote
      - gris:     fila cj - zj
    """
    def f(d):
        css = pd.DataFrame("", index=d.index, columns=d.columns)
        if entra is not None and entra in d.columns:
            css[entra] = f"background-color:#fff3b0;{ROJO}"
        if entra is not None and entra in d.index:
            css.loc[entra, :] = f"background-color:#cfe8ff;{ROJO}"
        if entra is not None and entra in d.index and entra in d.columns:
            css.loc[entra, entra] = f"background-color:#ffb347;{ROJO};font-weight:bold"
        css.loc["cj - zj", :] = f"background-color:#eeeeee;{ROJO};font-weight:bold"
        css["Solución"] = css["Solución"] + ";font-weight:bold"
        return css
    return df.style.apply(f, axis=None).format(asx.fmt)


def df_variables(x):
    filas = []
    for i, (nom, desc, c, grupo) in enumerate(asx.VARIABLES):
        filas.append([i + 1, nom, desc, float(x[i]), c, float(x[i] * c), grupo])
    return pd.DataFrame(filas, columns=["Nº", "Variable", "Descripción", "Valor (t)",
                                        "Costo unit. ($/t)", "Costo total ($)", "Grupo"])


def planes(x):
    """Plan de compra, de producción y de embarque (como las tablas 6.2 a 6.5 del libro)."""
    v = lambda n: float(x[asx.IDX[n]])

    compra = pd.DataFrame({"Pittsburgh": [v("IBP"), v("ICP")],
                           "Youngstown": [v("IBY"), v("ICY")]},
                          index=["Butte Minerals", "Cheyenne Mines"])
    compra["Total"] = compra.sum(axis=1)
    compra.loc["Total"] = compra.sum()

    produccion = pd.DataFrame(
        {"Pittsburgh - alto": [v("OBPH"), v("OCPH"), v("HP")],
         "Pittsburgh - bajo": [v("OBPL"), v("OCPL"), v("LP")],
         "Youngstown - alto": [v("OBYH"), v("OCYH"), v("HY")],
         "Youngstown - bajo": [v("OBYL"), v("OCYL"), v("LY")]},
        index=["Mineral de Butte", "Mineral de Cheyenne", "Acero producido"])

    filas = []
    for pais in ("J", "K", "T", "M"):
        for tipo in ("H", "L"):
            p, y = v(f"S{tipo}P{pais}"), v(f"S{tipo}Y{pais}")
            filas.append([asx.NOMBRE_PAIS[pais], asx.NOMBRE_TIPO[tipo], p, y, p + y,
                          asx.DEMANDA[(pais, tipo)]])
    embarque = pd.DataFrame(filas, columns=["País", "Tipo de acero", "Desde Pittsburgh",
                                            "Desde Youngstown", "Total", "Demanda"])
    return compra, produccion, embarque


def df_verificacion(A, x):
    filas = []
    for i, (n, desc, _, s, rhs) in enumerate(asx.RESTRICCIONES):
        lhs = float(A[i] @ x)
        if s == "<=":
            ok, holg = lhs <= rhs + 1e-6, rhs - lhs
        elif s == ">=":
            ok, holg = lhs >= rhs - 1e-6, lhs - rhs
        else:
            ok, holg = abs(lhs - rhs) < 1e-6, 0.0
        filas.append([n, desc, lhs, s, rhs, holg,
                      "Activa (se cumple justo)" if abs(holg) < 1e-6 else "Con holgura",
                      "OK" if ok else "FALLA"])
    return pd.DataFrame(filas, columns=["Nº", "Restricción", "Lado izq.", "Signo",
                                        "Lado der.", "Holgura", "Estado", "Cumple"])


def excel_en_memoria(datos, df_var, grupos):
    """Genera el Excel con todas las matrices y lo devuelve en bytes."""
    buf = io.BytesIO()
    with contextlib.redirect_stdout(io.StringIO()):      # exportar_excel imprime un aviso
        asx.exportar_excel(buf, datos["A"], datos["b"], datos["sentidos"],
                           datos["sim"], datos["res"], df_var, grupos)
    return buf.getvalue()


# =============================================================================
# 2. INTERFAZ
# =============================================================================
def pestana_modelo(datos):
    st.subheader("Modelo de programación lineal")
    st.markdown(
        "Es el modelo del estudio de caso del libro: **minimizar** el costo total sujeto a "
        "**28 restricciones** (1-2 compra, 3-4 capacidad, 5-8 mezcla, 9-12 balance de mineral, "
        "13-16 producción, 17-20 suministro en las prensas y 21-28 demandas) con "
        "**32 variables** no negativas.")
    st.caption("Las celdas azules son los coeficientes distintos de cero; la columna amarilla es el "
               "lado derecho (b).")
    df = df_modelo(datos["A"], datos["b"], datos["sentidos"])
    st.dataframe(estilo_modelo(df))
    st.markdown("**Vector de costos c ($/ton)** — compra + embarque del mineral, procesamiento y "
                "embarque del acero:")
    st.dataframe(pd.DataFrame([asx.COSTOS], index=["c"], columns=asx.NOMBRES).style.format(asx.fmt))


def pestana_pasos(datos):
    sim = datos["sim"]
    hist = sim.historial
    n1 = sum(1 for h in hist if h["fase"] == 1) - 1
    n2 = sum(1 for h in hist if h["fase"] == 2) - 1

    st.subheader("Matrices del método simplex (paso a paso)")
    st.markdown(
        f"El modelo tiene restricciones \"=\" y \"≥\", por eso se usa el **simplex de dos fases**: "
        f"la **Fase 1** ({n1} iteraciones) busca una solución factible y la **Fase 2** "
        f"({n2} iteraciones) minimiza el costo real.")

    with st.expander("¿Cómo leer cada matriz? (explicación desde cero)"):
        st.markdown(
            "1. **Filas**: cada fila es una restricción. La etiqueta de la izquierda es la "
            "*variable básica* de esa fila (la que vale lo que dice la columna *Solución*).\n"
            "2. **Última fila (cj - zj)**: dice cuánto baja el costo si una variable entra a la base. "
            "En minimización, si hay valores **negativos** todavía se puede mejorar.\n"
            "3. **Variable que entra**: la de cj - zj más negativo (columna amarilla).\n"
            "4. **Variable que sale**: se divide *Solución* entre la columna de la variable que entra "
            "(solo valores positivos) y gana la **razón mínima**.\n"
            "5. **Pivote**: cruce de la columna que entra con la fila que sale (celda naranja). "
            "Se divide su fila entre el pivote y se hace cero el resto de la columna.\n"
            "6. **Óptimo**: cuando todos los cj - zj son ≥ 0 ya no se puede reducir más el costo.\n\n"
            "En la tabla mostrada, la fila azul y la columna amarilla corresponden a la variable "
            "que acaba de entrar a la base. "
            "En la celda *Solución* de la fila cj - zj aparece el valor de **Z** (costo).")

    c1, c2 = st.columns([1, 3])
    with c1:
        fase = st.radio("Fase", ["Todas", "Fase 1", "Fase 2"], horizontal=True)
    indices = [i for i, h in enumerate(hist)
               if fase == "Todas" or h["fase"] == int(fase[-1])]
    with c2:
        pos = st.slider("Paso", 0, len(indices) - 1, 0,
                        help="Mueve el deslizador para recorrer las matrices")
    h = hist[indices[pos]]

    st.markdown(f"### Fase {h['fase']} — " +
                ("Tableau inicial" if h["it"] == 0 else f"Iteración {h['it']}"))
    if h["it"] == 0:
        st.info("Matriz inicial: la base está formada por las variables de holgura y artificiales. "
                + ("Se minimiza la suma de artificiales." if h["fase"] == 1
                   else "Se eliminan las artificiales y se usan los costos reales."))
    else:
        st.info(f"Entra **{h['entra']}**, sale **{h['sale']}**, pivote = {asx.fmt(h['pivote'])}.")
    st.metric("Valor de Z en este paso" if h["fase"] == 2 else "Suma de artificiales (Fase 1)",
              f"{h['z']:,.2f}")
    st.dataframe(estilo_tableau(h["df"], h["entra"]))


def pestana_solucion(datos, x):
    st.subheader("Solución óptima")
    solo_pos = st.checkbox("Mostrar solo las variables con valor mayor que cero", value=False)
    df = df_variables(x)
    if solo_pos:
        df = df[df["Valor (t)"] > 1e-9]
    st.dataframe(df.style.format({"Valor (t)": "{:,.2f}", "Costo unit. ($/t)": "{:,.2f}",
                                  "Costo total ($)": "{:,.2f}"}), height=420)
    st.info("Este problema tiene **varias soluciones óptimas** con el mismo costo. Por eso el reparto "
            "del acero a los países puede diferir de Solver y el costo total es idéntico.")

    compra, produccion, embarque = planes(x)
    st.markdown("#### Plan de compra de mineral (ton)")
    st.dataframe(compra.style.format("{:,.2f}"))
    st.markdown("#### Plan de producción: mineral usado y acero producido (ton)")
    st.dataframe(produccion.style.format("{:,.2f}"))
    st.markdown("#### Plan de embarque de acero (ton)")
    st.dataframe(embarque.style.format({c: "{:,.2f}" for c in embarque.columns[2:]}))


def pestana_costos(datos, x, grupos):
    st.subheader("Costos de la solución")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costo de compra", f"$ {grupos['Compra']:,.2f}")
    c2.metric("Costo de producción", f"$ {grupos['Producción']:,.2f}")
    c3.metric("Costo de distribución", f"$ {grupos['Distribución']:,.2f}")
    c4.metric("COSTO TOTAL", f"$ {grupos['TOTAL']:,.2f}")
    st.caption("Compra = mineral + embarque del mineral a las prensas. Producción = procesamiento en "
               "Pittsburgh y Youngstown. Distribución = embarque del acero a Japón, Corea, Taiwán y México. "
               "Total = suma de los tres.")
    tabla = pd.DataFrame({
        "Concepto": ["Costo de compra", "Costo de producción", "Costo de distribución", "COSTO TOTAL"],
        "Valor ($)": [grupos["Compra"], grupos["Producción"], grupos["Distribución"], grupos["TOTAL"]]})
    st.dataframe(tabla.style.format({"Valor ($)": "{:,.2f}"}))
    st.bar_chart(pd.Series({"Compra": grupos["Compra"], "Producción": grupos["Producción"],
                            "Distribución": grupos["Distribución"]}))

    st.markdown("#### Comparación con Solver de Excel")
    dif = abs(grupos["TOTAL"] - COSTO_SOLVER_EXCEL)
    st.write(f"Costo total con este algoritmo: **$ {grupos['TOTAL']:,.2f}**  \n"
             f"Costo total con Solver (Excel): **$ {COSTO_SOLVER_EXCEL:,.2f}**  \n"
             f"Diferencia: $ {dif:,.2f}")
    if dif < 0.01:
        st.success("Los resultados coinciden con Solver.")
    else:
        st.warning("Hay diferencia con el resultado de Solver; revisa los datos.")


def pestana_verificacion(datos, x):
    st.subheader("Verificación de las 28 restricciones")
    df = df_verificacion(datos["A"], x)
    if (df["Cumple"] == "OK").all():
        st.success("Se cumplen todas las restricciones.")
    else:
        st.error("Alguna restricción no se cumple.")
    st.dataframe(df.style.format({"Lado izq.": asx.fmt, "Lado der.": asx.fmt, "Holgura": asx.fmt}),
                 height=500)
    st.caption("\"Activa\" significa que la restricción se cumple justo en el límite (es la que "
               "limita el resultado). \"Con holgura\" significa que sobra margen.")


def main():
    st.set_page_config(page_title="American Steel Company - Simplex", layout="wide")
    st.title("American Steel Company")
    st.caption("Programación lineal por el método simplex (dos fases) — equivalente a Solver con "
               "\"Simplex LP\" de Excel, mostrando el procedimiento.")

    datos = cargar_datos()
    res = datos["res"]
    if res["estado"] != "optimo":
        st.error(f"El modelo no tiene solución óptima: {res['estado']}")
        return
    x = res["x"]
    grupos = asx.costos_resumen(x)

    tabs = st.tabs(["1. Modelo", "2. Matrices paso a paso", "3. Solución",
                    "4. Costos", "5. Verificación", "6. Descargar"])
    with tabs[0]:
        pestana_modelo(datos)
    with tabs[1]:
        pestana_pasos(datos)
    with tabs[2]:
        pestana_solucion(datos, x)
    with tabs[3]:
        pestana_costos(datos, x, grupos)
    with tabs[4]:
        pestana_verificacion(datos, x)
    with tabs[5]:
        st.subheader("Descargar resultados")
        st.write("Excel con el modelo, todas las matrices (tabla ), la solución y los costos.")
        st.download_button("Descargar Excel", data=excel_en_memoria(datos, df_variables(x), grupos),
                           file_name="resultados_american_steel.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@st.cache_resource(show_spinner="Resolviendo el modelo...")
def cargar_datos():
    return resolver_modelo()


if __name__ == "__main__":
    main()
