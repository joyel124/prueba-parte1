# Parte 1 — Listado de libros (Next.js + TypeScript + TailwindCSS)

Este entregable implementa un **listado de libros** consumiendo la API pública **Gutendex** con **Next.js 14 (App Router)** y **TypeScript**.  
Incluye **estados de carga y error**, UI responsiva con **TailwindCSS**, e íconos de **lucide-react**.

---

## Funcionalidad
- **Fetch** a `https://gutendex.com/books/?page=1` y render de los **10** primeros resultados.
- **Loading state**: spinner con mensaje.
- **Error state**: tarjeta centrada con icono y detalle del error (p. ej., `HTTP 500`).
- **Lista** en **grid** de tarjetas: título, primer autor (o “Autor desconocido”).
- **Accesibilidad** básica: jerarquía semántica, foco visual, contraste y `aria-hidden` en íconos decorativos.
- **Cancelación** de la petición con `AbortController` al desmontar el componente.
- **TypeScript estricto**: tipos `Author`, `Book`, `GutendexResponse`.

---

## Stack
- **Next.js 14+** (App Router) + **TypeScript**
- **TailwindCSS**
- **lucide-react** (íconos)

---

## Estructura relevante
```
/app
  page.tsx             # monta el componente BooksList
  layout.tsx           # fuentes + globals
  globals.css          # Tailwind base y estilos globales
/components
  BooksList.tsx         # lógica de fetch + UI (loading, error, grid)
```

---

## Ejecución local
1) **Instalar dependencias**
```bash
npm install
```
2) **Arrancar en desarrollo**
```bash
npm run dev
# http://localhost:3000
```
> Requiere conexión a Internet para consultar la API pública de Gutendex.

3) **Build de producción**
```bash
npm run build
npm run start
```