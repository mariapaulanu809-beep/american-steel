#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AMERICAN STEEL COMPANY - Programación lineal por el método SIMPLEX
===================================================================
Replica lo que hace Solver de Excel con "Simplex LP", pero mostrando el
procedimiento: matriz del modelo, tabla (matrices) de cada iteración,
solución final y costos (compra, producción, distribución y total).

Datos: Tablas 3.7, 3.8 y 3.9 del libro (Moncada) y el modelo matemático del
estudio de caso (restricciones 1 a 28).

Uso:
    python american_steel_simplex.py                  # resumen + tabla inicial y final
    python american_steel_simplex.py --tabla todos # imprime TODAS las matrices
    python american_steel_simplex.py --sin-excel      # no genera el archivo .xlsx

Método: Simplex de DOS FASES (porque el modelo tiene restricciones "=" y ">=").
    Fase 1: minimiza la suma de variables artificiales para hallar una solución
            factible inicial.
    Fase 2: con esa base factible, minimiza el costo total real.
Criterio (minimización): se entra con el cj - zj más negativo; se sale con la
prueba de la razón mínima; es óptimo cuando todos los cj - zj >= 0.
"""

import argparse
import sys
import numpy as np
import pandas as pd

TOL = 1e-9

# =============================================================================
# 1. DATOS DEL PROBLEMA (Tablas 3.7, 3.8 y 3.9 + suministros/capacidades)
# =============================================================================
# Tabla 3.7: compra de mineral y embarque a las prensas ($/ton)
COMPRA = {"Butte": 130, "Cheyenne": 110}
EMB_MINERAL = {("Butte", "P"): 10, ("Butte", "Y"): 13,
               ("Cheyenne", "P"): 14, ("Cheyenne", "Y"): 17}
# Tabla 3.8: costo de procesamiento ($/ton)  H = alto calibre, L = bajo calibre
PROCESO = {("H", "P"): 32, ("H", "Y"): 39, ("L", "P"): 27, ("L", "Y"): 32}
# Tabla 3.9: demanda (ton) por país y tipo de acero
DEMANDA = {("J", "H"): 400, ("J", "L"): 200, ("K", "H"): 200, ("K", "L"): 100,
           ("T", "H"): 200, ("T", "L"): 100, ("M", "H"): 150, ("M", "L"): 50}
# Tabla 3.9: embarque de acero ($/ton)  (tipo, prensa, país)
EMB_ACERO = {("H", "P", "J"): 110, ("H", "Y", "J"): 115,
             ("L", "P", "J"): 100, ("L", "Y", "J"): 110,
             ("H", "P", "K"): 140, ("H", "Y", "K"): 150,
             ("L", "P", "K"): 130, ("L", "Y", "K"): 145,
             ("H", "P", "T"): 130, ("H", "Y", "T"): 135,
             ("L", "P", "T"): 125, ("L", "Y", "T"): 127,
             ("H", "P", "M"): 80,  ("H", "Y", "M"): 90,
             ("L", "P", "M"): 80,  ("L", "Y", "M"): 85}
SUMINISTRO = {"Butte": 1000, "Cheyenne": 2000}      # restricciones (1) y (2)
CAPACIDAD = {"P": 700, "Y": 1500}                   # restricciones (3) y (4)
MEZCLA = {"H": 2, "L": 3}   # alto: 2 de Cheyenne por 1 de Butte; bajo: 3 por 1

NOMBRE_PAIS = {"J": "Japón", "K": "Corea", "T": "Taiwán", "M": "México"}
NOMBRE_PRENSA = {"P": "Pittsburgh", "Y": "Youngstown"}
NOMBRE_TIPO = {"H": "alto calibre", "L": "bajo calibre"}

# =============================================================================
# 2. VARIABLES DE DECISIÓN (mismo orden y nombres que el libro y el Excel)
# =============================================================================
# (nombre, descripción, costo unitario, grupo de costo)
VARIABLES = []


def _agregar(nombre, desc, costo, grupo):
    VARIABLES.append((nombre, desc, float(costo), grupo))


# Compra de mineral (incluye embarque del mineral a la prensa)
for (mina, prensa), letra in [(("Butte", "P"), "IBP"), (("Butte", "Y"), "IBY"),
                              (("Cheyenne", "P"), "ICP"), (("Cheyenne", "Y"), "ICY")]:
    _agregar(letra, f"Mineral de {mina} comprado y embarcado a {NOMBRE_PRENSA[prensa]}",
             COMPRA[mina] + EMB_MINERAL[(mina, prensa)], "Compra")

# Producción de acero en cada prensa
for (tipo, prensa), letra in [(("H", "P"), "HP"), (("L", "P"), "LP"),
                              (("H", "Y"), "HY"), (("L", "Y"), "LY")]:
    _agregar(letra, f"Acero {NOMBRE_TIPO[tipo]} producido en {NOMBRE_PRENSA[prensa]}",
             PROCESO[(tipo, prensa)], "Producción")

# Mineral usado en cada prensa por tipo de acero (sin costo propio)
for prensa, tipo, mina, letra in [
        ("P", "H", "Butte", "OBPH"), ("P", "H", "Cheyenne", "OCPH"),
        ("P", "L", "Butte", "OBPL"), ("P", "L", "Cheyenne", "OCPL"),
        ("Y", "H", "Butte", "OBYH"), ("Y", "H", "Cheyenne", "OCYH"),
        ("Y", "L", "Butte", "OBYL"), ("Y", "L", "Cheyenne", "OCYL")]:
    _agregar(letra, f"Mineral de {mina} usado en {NOMBRE_PRENSA[prensa]} para acero {NOMBRE_TIPO[tipo]}",
             0, "Uso de mineral")

# Distribución de acero: SHPJ, SHPK, ... (S + tipo + prensa + país)
for tipo in ("H", "L"):
    for prensa in ("P", "Y"):
        for pais in ("J", "K", "T", "M"):
            _agregar(f"S{tipo}{prensa}{pais}",
                     f"Acero {NOMBRE_TIPO[tipo]} de {NOMBRE_PRENSA[prensa]} a {NOMBRE_PAIS[pais]}",
                     EMB_ACERO[(tipo, prensa, pais)], "Distribución")

# El libro/Excel ordenan la distribución: alto calibre (P y Y) y luego bajo calibre.
# El ciclo anterior ya genera ese orden: SHPJ..SHPM, SHYJ..SHYM, SLPJ..SLPM, SLYJ..SLYM.

NOMBRES = [v[0] for v in VARIABLES]
IDX = {n: i for i, n in enumerate(NOMBRES)}
COSTOS = np.array([v[2] for v in VARIABLES])
N_VAR = len(VARIABLES)

# =============================================================================
# 3. RESTRICCIONES (1) a (28) del modelo matemático del libro
# =============================================================================
RESTRICCIONES = []   # (nº, descripción, {variable: coef}, sentido, rhs)


def restr(desc, coefs, sentido, rhs):
    RESTRICCIONES.append((len(RESTRICCIONES) + 1, desc, coefs, sentido, float(rhs)))


# --- Compra
restr("Suministro de Butte Minerals", {"IBP": 1, "IBY": 1}, "<=", SUMINISTRO["Butte"])
restr("Suministro de Cheyenne Mines", {"ICP": 1, "ICY": 1}, "<=", SUMINISTRO["Cheyenne"])
# --- Capacidad de minerales
restr("Capacidad de mineral, prensa Pittsburgh",
      {"OBPH": 1, "OBPL": 1, "OCPH": 1, "OCPL": 1}, "<=", CAPACIDAD["P"])
restr("Capacidad de mineral, prensa Youngstown",
      {"OBYH": 1, "OBYL": 1, "OCYH": 1, "OCYL": 1}, "<=", CAPACIDAD["Y"])
# --- Requerimientos de mezcla (Cheyenne = k * Butte)
restr("Mezcla alto calibre en Pittsburgh", {"OCPH": 1, "OBPH": -MEZCLA["H"]}, "=", 0)
restr("Mezcla bajo calibre en Pittsburgh", {"OCPL": 1, "OBPL": -MEZCLA["L"]}, "=", 0)
restr("Mezcla alto calibre en Youngstown", {"OCYH": 1, "OBYH": -MEZCLA["H"]}, "=", 0)
restr("Mezcla bajo calibre en Youngstown", {"OCYL": 1, "OBYL": -MEZCLA["L"]}, "=", 0)
# --- Balance producción y compra
restr("Mineral de Butte usado en Pittsburgh", {"OBPH": 1, "OBPL": 1, "IBP": -1}, "=", 0)
restr("Mineral de Cheyenne usado en Pittsburgh", {"OCPH": 1, "OCPL": 1, "ICP": -1}, "=", 0)
restr("Mineral de Butte usado en Youngstown", {"OBYH": 1, "OBYL": 1, "IBY": -1}, "=", 0)
restr("Mineral de Cheyenne usado en Youngstown", {"OCYH": 1, "OCYL": 1, "ICY": -1}, "=", 0)
# --- Equilibrio de producción
restr("Acero alto calibre producido en Pittsburgh", {"OCPH": 1, "OBPH": 1, "HP": -1}, "=", 0)
restr("Acero bajo calibre producido en Pittsburgh", {"OCPL": 1, "OBPL": 1, "LP": -1}, "=", 0)
restr("Acero alto calibre producido en Youngstown", {"OCYH": 1, "OBYH": 1, "HY": -1}, "=", 0)
restr("Acero bajo calibre producido en Youngstown", {"OCYL": 1, "OBYL": 1, "LY": -1}, "=", 0)
# --- Suministros en las prensas (lo embarcado = lo producido)
restr("Alto calibre embarcado desde Pittsburgh",
      {"SHPJ": 1, "SHPK": 1, "SHPT": 1, "SHPM": 1, "HP": -1}, "=", 0)
restr("Bajo calibre embarcado desde Pittsburgh",
      {"SLPJ": 1, "SLPK": 1, "SLPT": 1, "SLPM": 1, "LP": -1}, "=", 0)
restr("Alto calibre embarcado desde Youngstown",
      {"SHYJ": 1, "SHYK": 1, "SHYT": 1, "SHYM": 1, "HY": -1}, "=", 0)
restr("Bajo calibre embarcado desde Youngstown",
      {"SLYJ": 1, "SLYK": 1, "SLYT": 1, "SLYM": 1, "LY": -1}, "=", 0)
# --- Demandas (>=)
for pais, tipo in [("J", "H"), ("J", "L"), ("K", "H"), ("K", "L"),
                   ("T", "H"), ("T", "L"), ("M", "H"), ("M", "L")]:
    restr(f"Demanda de acero {NOMBRE_TIPO[tipo]} en {NOMBRE_PAIS[pais]}",
          {f"S{tipo}P{pais}": 1, f"S{tipo}Y{pais}": 1}, ">=", DEMANDA[(pais, tipo)])

M_REST = len(RESTRICCIONES)


# =============================================================================
# 4. UTILIDADES DE IMPRESIÓN
# =============================================================================
def fmt(x):
    """Formato numérico compacto: enteros sin decimales, el resto con 4."""
    if abs(x) < 5e-10:
        return "0"
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x))}"
    return f"{x:.4f}"


def imprimir_df(df, ancho_bloque=10, ultima_col_fija=True):
    """Imprime un DataFrame ancho en bloques de columnas (repite la última)."""
    cols = list(df.columns)
    fija = [cols[-1]] if ultima_col_fija else []
    datos = cols[:-1] if ultima_col_fija else cols
    for k in range(0, len(datos), ancho_bloque):
        bloque = datos[k:k + ancho_bloque] + fija
        print(df[bloque].to_string())
        print()


def titulo(txt, car="="):
    print("\n" + car * 100)
    print(txt)
    print(car * 100)


# =============================================================================
# 5. CONSTRUCCIÓN DE LA FORMA ESTÁNDAR
# =============================================================================
def construir_modelo():
    """Devuelve A, b, sentidos (matriz original del modelo)."""
    A = np.zeros((M_REST, N_VAR))
    b = np.zeros(M_REST)
    sentidos = []
    for i, (_, _, coefs, sentido, rhs) in enumerate(RESTRICCIONES):
        for var, c in coefs.items():
            A[i, IDX[var]] = c
        b[i] = rhs
        sentidos.append(sentido)
    return A, b, sentidos


def forma_estandar(A, b, sentidos):
    """
    Agrega variables de holgura (<=), de exceso (>=) y artificiales (= y >=).
    Devuelve la matriz ampliada, nombres de columnas y la base inicial.
    """
    m, n = A.shape
    nombres = list(NOMBRES)
    extra_cols = []
    base = [None] * m
    tipo_col = ["decision"] * n

    # Primero holguras / excesos
    for i, s in enumerate(sentidos):
        if s == "<=":
            col = np.zeros(m); col[i] = 1
            nombres.append(f"h{i + 1}"); tipo_col.append("holgura")
            extra_cols.append(col)
        elif s == ">=":
            col = np.zeros(m); col[i] = -1
            nombres.append(f"e{i + 1}"); tipo_col.append("exceso")
            extra_cols.append(col)
    # Luego artificiales para filas "=" y ">="
    for i, s in enumerate(sentidos):
        if s in ("=", ">="):
            col = np.zeros(m); col[i] = 1
            nombres.append(f"a{i + 1}"); tipo_col.append("artificial")
            extra_cols.append(col)

    Aext = np.hstack([A, np.array(extra_cols).T])
    # base inicial: holgura (<=) o artificial (=, >=)
    for j, nm in enumerate(nombres):
        if nm.startswith("h") and tipo_col[j] == "holgura":
            base[int(nm[1:]) - 1] = j
        elif nm.startswith("a") and tipo_col[j] == "artificial":
            base[int(nm[1:]) - 1] = j
    return Aext, nombres, tipo_col, base


# =============================================================================
# 6. SIMPLEX DE DOS FASES CON TABLA
# =============================================================================
class Simplex:
    def __init__(self, A, b, sentidos, c):
        self.Aext, self.nombres, self.tipo, self.base = forma_estandar(A, b, sentidos)
        self.m, self.ncols = self.Aext.shape
        self.b = b.copy()
        self.c = c.copy()
        self.historial = []          # lista de dicts con cada tabla
        self.iter_global = 0

    # ---- armado y vistas del tabla
    def _tabla_inicial(self, costos):
        m, n = self.Aext.shape
        T = np.zeros((m + 1, n + 1))
        T[:m, :n] = self.Aext
        T[:m, n] = self.b
        cb = costos[self.base]
        T[m, :n] = costos - cb @ T[:m, :n]
        T[m, n] = -cb @ self.b
        return T

    def _df(self, T, columnas, base, nombres):
        m = len(base)
        idx = [nombres[j] for j in base] + ["cj - zj"]
        cols = [nombres[j] for j in columnas] + ["Solución"]
        datos = np.vstack([
            np.column_stack([T[:m, columnas], T[:m, -1]]),
            np.append(T[m, columnas], -T[m, -1])      # en la celda Solución: valor de Z
        ])
        datos = np.where(np.abs(datos) < 5e-10, 0.0, datos)
        return pd.DataFrame(datos, index=idx, columns=cols)

    def _guardar(self, T, columnas, base, nombres, fase, it, info, entra=None, sale=None, pivote=None):
        self.historial.append(dict(
            fase=fase, it=it, info=info, z=-T[-1, -1],
            entra=entra, sale=sale, pivote=pivote,
            df=self._df(T, columnas, base, nombres)))

    # ---- pivoteo
    @staticmethod
    def _pivotear(T, r, c):
        T[r, :] = T[r, :] / T[r, c]
        for i in range(T.shape[0]):
            if i != r and abs(T[i, c]) > 0:
                T[i, :] -= T[i, c] * T[r, :]

    def _iterar(self, T, columnas, base, nombres, fase, verbose, max_iter=2000):
        it = 0
        degeneradas = 0
        while True:
            d = T[-1, :-1]
            cand = [j for j in columnas if d[j] < -TOL]
            if not cand:
                return "optimo"
            # Regla de Dantzig (más negativo); Bland si hay muchas degeneradas
            if degeneradas > 50:
                j = min(cand)
            else:
                j = min(cand, key=lambda k: (d[k], k))
            col = T[:-1, j]
            filas = [i for i in range(len(base)) if col[i] > TOL]
            if not filas:
                return "no_acotado"
            razones = {i: T[i, -1] / col[i] for i in filas}
            rmin = min(razones.values())
            empatadas = [i for i in filas if abs(razones[i] - rmin) < 1e-9]
            r = min(empatadas, key=lambda i: base[i])        # desempate tipo Bland
            degeneradas = degeneradas + 1 if rmin < 1e-9 else 0

            sale = nombres[base[r]]
            entra = nombres[j]
            piv = T[r, j]
            self._pivotear(T, r, j)
            base[r] = j
            it += 1
            self.iter_global += 1
            info = (f"Entra {entra} | Sale {sale} | Pivote = {fmt(piv)} "
                    f"(fila {r + 1}) | razón mínima = {fmt(rmin)}")
            self._guardar(T, columnas, base, nombres, fase, it, info,
                          entra=entra, sale=sale, pivote=piv)
            if verbose:
                print(f"  Fase {fase} - Iteración {it:>3}: {info} | Z = {fmt(-T[-1, -1])}")
            if it > max_iter:
                return "max_iter"

    # ---- resolución completa
    def resolver(self, verbose=True):
        nombres = self.nombres
        n = self.ncols
        art = [j for j in range(n) if self.tipo[j] == "artificial"]
        no_art = [j for j in range(n) if self.tipo[j] != "artificial"]

        # ---------------- FASE 1
        c1 = np.zeros(n)
        c1[art] = 1.0
        T = self._tabla_inicial(c1)
        base = list(self.base)
        self._guardar(T, list(range(n)), base, nombres, 1, 0, "Tabla inicial (Fase 1)")
        if verbose:
            titulo("FASE 1: minimizar la suma de variables artificiales", "-")
        estado = self._iterar(T, list(range(n)), base, nombres, 1, verbose)
        z1 = -T[-1, -1]
        if estado != "optimo" or z1 > 1e-7:
            return dict(estado="infactible", z=None)
        if verbose:
            print(f"\n  Fase 1 terminó con suma de artificiales = {fmt(z1)} -> el modelo es FACTIBLE.")

        # Sacar artificiales que quedaron en la base (a nivel cero)
        filas_borrar = []
        for r in range(len(base)):
            if base[r] in art:
                piv = [j for j in no_art if abs(T[r, j]) > 1e-9]
                if piv:
                    self._pivotear(T, r, piv[0]); base[r] = piv[0]
                else:
                    filas_borrar.append(r)          # fila redundante
        if filas_borrar:
            keep = [i for i in range(T.shape[0]) if i not in filas_borrar]
            T = T[keep, :]
            base = [base[i] for i in range(len(base)) if i not in filas_borrar]

        # ---------------- FASE 2
        c2 = np.zeros(n)
        c2[:N_VAR] = self.c
        T2 = np.zeros((len(base) + 1, n + 1))
        T2[:len(base), :] = T[:len(base), :]
        cb = c2[base]
        T2[-1, :n] = c2 - cb @ T2[:len(base), :n]
        T2[-1, -1] = -cb @ T2[:len(base), -1]
        self._guardar(T2, no_art, base, nombres, 2, 0, "Tabla inicial (Fase 2)")
        if verbose:
            titulo("FASE 2: minimizar el costo total", "-")
        estado = self._iterar(T2, no_art, base, nombres, 2, verbose)
        if estado != "optimo":
            return dict(estado=estado, z=None)

        x = np.zeros(n)
        for r, j in enumerate(base):
            x[j] = T2[r, -1]
        self.T_final, self.base_final, self.cols_final = T2, base, no_art
        return dict(estado="optimo", z=-T2[-1, -1], x=x[:N_VAR], x_completo=x)


# =============================================================================
# 7. REPORTES
# =============================================================================
def reporte_modelo(A, b, sentidos):
    titulo("MATRIZ DEL MODELO  [A | sentido | b]   (28 restricciones x 32 variables)")
    filas = [f"({r[0]}) {r[1][:42]}" for r in RESTRICCIONES]
    df = pd.DataFrame(A, index=filas, columns=NOMBRES)
    df["sentido"] = sentidos
    df["b"] = b
    df = df.map(lambda v: fmt(v) if isinstance(v, (int, float, np.floating)) else v)
    imprimir_df(df[NOMBRES + ["b"]].assign(), ancho_bloque=11)
    print("Vector de costos c (costo unitario de cada variable, $/ton):")
    print(pd.Series(COSTOS, index=NOMBRES).map(fmt).to_frame("c").T.to_string())


def reporte_resultados(x):
    titulo("SOLUCIÓN ÓPTIMA - VARIABLES DE DECISIÓN")
    filas = []
    for i, (nom, desc, c, grupo) in enumerate(VARIABLES):
        filas.append([i + 1, nom, desc, x[i], c, x[i] * c, grupo])
    df = pd.DataFrame(filas, columns=["Nº", "Variable", "Descripción", "Valor (t)",
                                      "Costo unit. ($/t)", "Costo total ($)", "Grupo"])
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    out = df.copy()
    for col in ["Valor (t)", "Costo unit. ($/t)", "Costo total ($)"]:
        out[col] = out[col].map(lambda v: f"{v:,.2f}")
    print(out.to_string(index=False))
    return df


def costos_resumen(x):
    grupos = {"Compra": 0.0, "Producción": 0.0, "Distribución": 0.0}
    for i, (_, _, c, g) in enumerate(VARIABLES):
        if g in grupos:
            grupos[g] += x[i] * c
    grupos["TOTAL"] = sum(grupos.values())
    return grupos


def reporte_costos(x):
    g = costos_resumen(x)
    titulo("RESUMEN DE COSTOS")
    print(f"  Costo de compra (mineral + embarque del mineral) : $ {g['Compra']:>14,.2f}")
    print(f"  Costo de producción (procesamiento en prensas)  : $ {g['Producción']:>14,.2f}")
    print(f"  Costo de distribución del acero                 : $ {g['Distribución']:>14,.2f}")
    print("  " + "-" * 68)
    print(f"  COSTO TOTAL (suma de los tres)                  : $ {g['TOTAL']:>14,.2f}")
    return g


def reporte_planes(x):
    v = lambda n: x[IDX[n]]
    titulo("PLANES DE LA SOLUCIÓN ÓPTIMA (equivalentes a las Tablas 6.2 a 6.5 del libro)")

    print("\nPlan de compra de mineral (ton):")
    df = pd.DataFrame({"Pittsburgh": [v("IBP"), v("ICP")], "Youngstown": [v("IBY"), v("ICY")]},
                      index=["Butte Minerals", "Cheyenne Mines"])
    df["Total"] = df.sum(axis=1)
    df.loc["Total"] = df.sum()
    print(df.map(fmt).to_string())

    print("\nPlan de producción (ton de acero) y mineral usado:")
    df = pd.DataFrame(
        {"Pitts. alto": [v("OBPH"), v("OCPH"), v("HP")],
         "Pitts. bajo": [v("OBPL"), v("OCPL"), v("LP")],
         "Youngs. alto": [v("OBYH"), v("OCYH"), v("HY")],
         "Youngs. bajo": [v("OBYL"), v("OCYL"), v("LY")]},
        index=["Mineral Butte", "Mineral Cheyenne", "Acero producido"])
    print(df.map(fmt).to_string())

    print("\nPlan de embarque de acero (ton):")
    filas = []
    for pais in ("J", "K", "T", "M"):
        for tipo in ("H", "L"):
            p, y = v(f"S{tipo}P{pais}"), v(f"S{tipo}Y{pais}")
            filas.append([NOMBRE_PAIS[pais], NOMBRE_TIPO[tipo], fmt(p), fmt(y),
                          fmt(p + y), DEMANDA[(pais, tipo)]])
    print(pd.DataFrame(filas, columns=["País", "Tipo", "Desde Pittsburgh",
                                       "Desde Youngstown", "Total", "Demanda"]).to_string(index=False))


def verificar_restricciones(A, b, sentidos, x):
    titulo("VERIFICACIÓN DE RESTRICCIONES (¿se cumplen las 28?)")
    filas = []
    ok_total = True
    for i, (n, desc, _, s, rhs) in enumerate(RESTRICCIONES):
        lhs = A[i] @ x
        if s == "<=":
            ok, holg = lhs <= rhs + 1e-6, rhs - lhs
        elif s == ">=":
            ok, holg = lhs >= rhs - 1e-6, lhs - rhs
        else:
            ok, holg = abs(lhs - rhs) < 1e-6, 0.0
        ok_total &= ok
        filas.append([n, desc[:44], fmt(lhs), s, fmt(rhs), fmt(holg),
                      "Activa" if abs(holg) < 1e-6 else "Holgura", "OK" if ok else "FALLA"])
    print(pd.DataFrame(filas, columns=["Nº", "Restricción", "Lado izq.", "", "Lado der.",
                                       "Holgura", "Estado", "Cumple"]).to_string(index=False))
    print("\n  >>> Todas las restricciones se cumplen." if ok_total
          else "\n  >>> ¡Alguna restricción NO se cumple!")


def validar_con_scipy(A, b, sentidos, z_propio):
    """Comprobación independiente con scipy (HiGHS), como si fuera Solver."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        print("\n(scipy no está instalado: se omite la verificación cruzada)")
        return
    Aub, bub, Aeq, beq = [], [], [], []
    for i, s in enumerate(sentidos):
        if s == "<=":
            Aub.append(A[i]); bub.append(b[i])
        elif s == ">=":
            Aub.append(-A[i]); bub.append(-b[i])
        else:
            Aeq.append(A[i]); beq.append(b[i])
    res = linprog(COSTOS, A_ub=np.array(Aub), b_ub=bub, A_eq=np.array(Aeq),
                  b_eq=beq, bounds=(0, None), method="highs")
    titulo("VERIFICACIÓN CRUZADA")
    print(f"  Costo total del simplex propio : $ {z_propio:,.2f}")
    print(f"  Costo total de scipy (HiGHS)   : $ {res.fun:,.2f}")
    print(f"  Diferencia                     : $ {abs(z_propio - res.fun):.6f}")
    print("  Resultado de Solver en Excel   : $ 392,416.67  (Moncada_tablas_pro.xlsx)")


# =============================================================================
# 8. EXPORTACIÓN A EXCEL
# =============================================================================
def exportar_excel(ruta, A, b, sentidos, sim, res, df_var, grupos):
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        # Modelo
        dfm = pd.DataFrame(A, index=[f"({r[0]}) {r[1]}" for r in RESTRICCIONES], columns=NOMBRES)
        dfm.insert(len(NOMBRES), "Sentido", sentidos)
        dfm["b"] = b
        dfm.loc["Costo c ($/t)"] = list(COSTOS) + ["", ""]
        dfm.to_excel(w, sheet_name="Modelo (A,b,c)")

        # Tabla apilados
        hoja = "Tabla"
        fila = 0
        pd.DataFrame({"Matrices (tabla) del método simplex": [
            "Fase 1: minimiza la suma de artificiales. Fase 2: minimiza el costo total.",
            "Última fila = cj - zj; en la columna Solución de esa fila aparece el valor de Z."]}
        ).to_excel(w, sheet_name=hoja, startrow=fila, index=False)
        fila += 4
        for h in sim.historial:
            enc = pd.DataFrame({f"FASE {h['fase']} - Iteración {h['it']}: {h['info']}  | Z = {fmt(h['z'])}": []})
            enc.to_excel(w, sheet_name=hoja, startrow=fila, index=False)
            h["df"].to_excel(w, sheet_name=hoja, startrow=fila + 1)
            fila += len(h["df"]) + 4

        # Solución y costos
        df_var.to_excel(w, sheet_name="Solución", index=False)
        pd.DataFrame({"Concepto": ["Costo de compra (mineral + embarque)", "Costo de producción",
                                   "Costo de distribución del acero", "COSTO TOTAL"],
                      "Valor ($)": [grupos["Compra"], grupos["Producción"],
                                    grupos["Distribución"], grupos["TOTAL"]]}
                     ).to_excel(w, sheet_name="Costos", index=False)

        # Ajuste de formato básico
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
        for ws in w.book.worksheets:
            ws.column_dimensions["A"].width = 52 if ws.title != "Costos" else 40
            for k in range(2, ws.max_column + 1):
                ws.column_dimensions[get_column_letter(k)].width = 13
            for celda in ws[1]:
                celda.font = Font(bold=True)
        w.book["Costos"].column_dimensions["B"].width = 18
        w.book["Solución"].column_dimensions["C"].width = 70
    print(f"\nArchivo Excel generado: {ruta}")


# =============================================================================
# 9. PROGRAMA PRINCIPAL
# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="American Steel Company - Simplex de dos fases")
    ap.add_argument("--tabla", choices=["basicos", "todos", "ninguno"], default="basicos",
                    help="basicos: inicial y final de cada fase | todos: cada iteración")
    ap.add_argument("--sin-excel", action="store_true", help="no generar el archivo Excel")
    ap.add_argument("--salida", default="resultados_american_steel.xlsx")
    args = ap.parse_args()

    pd.set_option("display.width", 250)

    A, b, sentidos = construir_modelo()
    reporte_modelo(A, b, sentidos)

    titulo("PASO A PASO DEL MÉTODO SIMPLEX")
    sim = Simplex(A, b, sentidos, COSTOS)
    res = sim.resolver(verbose=True)
    if res["estado"] != "optimo":
        print(f"\nEl modelo no tiene solución óptima: {res['estado']}")
        sys.exit(1)

    # Impresión de matrices (tabla)
    h = sim.historial
    if args.tabla != "ninguno":
        if args.tabla == "todos":
            mostrar = h
        else:
            f1 = [x for x in h if x["fase"] == 1]
            f2 = [x for x in h if x["fase"] == 2]
            mostrar = [f1[0], f1[-1], f2[0], f2[-1]]
        for t in mostrar:
            titulo(f"MATRIZ (tabla) - Fase {t['fase']}, iteración {t['it']}: {t['info']}  | Z = {fmt(t['z'])}", "~")
            imprimir_df(t["df"].map(fmt), ancho_bloque=12)

    x = res["x"]
    print(f"\nIteraciones totales: {sim.iter_global} "
          f"(Fase 1: {sum(1 for t in h if t['fase'] == 1) - 1}, "
          f"Fase 2: {sum(1 for t in h if t['fase'] == 2) - 1})")

    df_var = reporte_resultados(x)
    reporte_planes(x)
    grupos = reporte_costos(x)
    verificar_restricciones(A, b, sentidos, x)
    validar_con_scipy(A, b, sentidos, res["z"])

    if not args.sin_excel:
        exportar_excel(args.salida, A, b, sentidos, sim, res, df_var, grupos)


if __name__ == "__main__":
    main()
