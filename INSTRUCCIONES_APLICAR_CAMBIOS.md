# Aplicar los cambios del observatorio

1. Descarga y descomprime el ZIP de cambios.
2. Copia su contenido en la raíz del repositorio `observatorio-de-datos-departamental`, conservando las carpetas y aceptando reemplazar los archivos existentes.
3. Verifica que los CSV queden en `data/respaldo/` (dentro de la raíz del repositorio), junto a los respaldos que ya existían.
4. En GitHub Desktop revisa los cambios, escribe un resumen como `Agrega indicadores laborales, fiscales y climáticos`, confirma y pulsa **Push origin**.
5. Streamlit Community Cloud reconstruirá la aplicación desde el repositorio. Si falla la instalación, revisa el log de despliegue y que `requirements.txt` también se haya actualizado.

El paquete contiene solamente archivos de aplicación, documentación y respaldos oficiales curados. No incluye la carpeta temporal `tmp_source/` ni los originales de descarga.

## Alcance de datos

La evaluación de fuentes y los límites metodológicos están en `VIABILIDAD_NUEVAS_VARIABLES.md`. Informalidad, brecha salarial y dinámica empresarial quedan señaladas como pendientes porque no se encontró una serie oficial departamental homogénea y estable que permita compararlas sin introducir proxies. El resumen IDEAM 2025 no publica el valor de Nariño; la serie departamental de bosque se mantiene hasta 2024.