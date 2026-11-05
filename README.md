# AnalisisR 1.0

Aplicación de escritorio independiente para preparar datos, conversar con un
endpoint de IA y ejecutar análisis locales con R. Es autónoma: los módulos de datos,
conexiones, cifrado y procesos viven en este directorio y no dependen de ningún otro
proyecto.

**Requiere R instalado.** AnalisisR no incluye R ni lo empaqueta: todos los
procedimientos estadísticos se calculan en R y no hay alternativa en Python. Sin R
la aplicación abre únicamente la pestaña **Entorno R**, avisa de la instalación
necesaria y no permite ninguna operación.

## Características

### Datos

- Importa CSV, TXT y TSV con Python, y Excel, SPSS, Stata y SAS a través de R
  (`readxl`, `haven`), conservando etiquetas de variable y de valor.
- Niveles de medida revisables por variable (identificador, binaria, nominal, ordinal,
  continua, texto). Los que declares se guardan en un archivo `.analisisr.json` junto a tus
  datos y se recuperan al volver a importarlos.
- Recodificación por reglas legibles, fusión de categorías ordinales poco frecuentes y
  selección de variables. Todo se aplica **sobre una copia**: el archivo original nunca se
  modifica.
- Las variables binarias se recodifican a 0 y 1 con su primera categoría como referencia, y
  las etiquetas de valor se reasignan a los códigos nuevos.
- Lista de los cinco últimos archivos importados, conservada entre sesiones.

### Conversación con la IA

- Proveedores: servidor local (llama-server), OpenAI, DeepSeek, Anthropic y Google Gemini,
  además del modo sin IA. Modelo, límite de salida y tiempo por operación editables.
- El razonamiento se solicita **desactivado** en todos los proveedores; si el servidor
  informa de tokens de pensamiento, la respuesta se rechaza.
- Las claves se guardan con el gestor de credenciales del sistema, DPAPI en Windows o
  Fernet en los demás; nunca viajan en las sesiones guardadas ni en las peticiones.
- El endpoint recibe el **diccionario de variables sin filas** y la conversación. Enviarle
  la salida de R es una casilla independiente que puedes desmarcar para que los resultados
  no salgan del equipo.

### Análisis con R

- 27 plantillas de consulta que detallan estimandos, supuestos, contrastes,
  diagnósticos, tamaños de efecto e interpretación, y que se rellenan con tus variables
  reales desde un formulario.
- La sintaxis del código generado se comprueba localmente antes de ejecutarlo; los errores
  se devuelven para corregirlos, con un máximo de tres fallos sintácticos consecutivos.
- Hasta seis bloques de R y tres consultas de ayuda por turno, cada bloque autocontenido y
  en una sesión nueva de R.
- Los resultados se presentan en tablas; la notación LaTeX habitual se convierte a símbolos
  legibles sin necesidad de instalar TeX.
- Diagnóstico del entorno: versión de R, bibliotecas y estado de los 25 paquetes que pueden
  necesitar las plantillas, sin instalar nada ni conectarse a la red.

### Sesiones, informes y privacidad

- Sesiones portables `.analisisr` con el origen, los datos tratados, las reglas, la
  conversación, los scripts y las salidas. No incluyen claves.
- Exportación del informe a Word (`.docx`) con preguntas, interpretación, tablas editables
  y el código R, generada sin dependencias externas.
- Todos los temporales se crean dentro de la carpeta del programa y se eliminan al terminar
  cada operación y al cerrar.

### Plantillas disponibles

| Familia | Plantillas |
| --- | --- |
| **Exploración y descripción** | Ausentes e imputación múltiple, Correlación, Descriptivos, Tablas de contingencia |
| **Comparación de medias y diseños** | ANCOVA, ANOVA, ANOVA de medidas repetidas, Antes y después, Diferencia entre medias |
| **Regresión y modelos** | Mediación, Modelo multinivel, Moderación, Regresión, Regresión logística, Regresión multinomial, Regresión ordinal, Regresión para recuentos |
| **Medida, fiabilidad y validez** | Acuerdo entre evaluaciones, Análisis factorial confirmatorio, Análisis factorial exploratorio, Consistencia interna, Fiabilidad, Invarianza de medida |
| **Clasificación, pronóstico y agrupación** | Análisis clúster, Análisis de supervivencia, Análisis discriminante, Curva ROC y capacidad diagnóstica |

La [guía completa](assets/guia.html) documenta cada plantilla, el catálogo de
procedimientos y la preparación de los paquetes de R. Se abre desde la propia aplicación
con **F1**.

## Instalación y ejecución

Requiere Python 3.10 o posterior:

```powershell
python -m pip install -r requirements.txt
python AnalisisR.py
```

Mantén juntos `AnalisisR.py`, `analisisr_core.py`, `analisisr_ui.py`,
`analisisr_secrets.py`, `analisisr_session.py` y `analisisr_docx.py`, junto con
la carpeta `assets/`. No hace falta configurar
`PYTHONPATH`. Abre la guía local desde **Ayuda → Guía de AnalisisR** o con **F1**;
también puedes abrir directamente [assets/guia.html](assets/guia.html).

La primera pestaña, **Entorno R**, muestra el estado del entorno: ruta de `Rscript`,
versión de R, bibliotecas y paquetes instalados con **Comprobar R y paquetes**. R se
busca, por orden, en la variable `R_HOME`, en la carpeta que indiques en esa pestaña,
en el `PATH` y en las instalaciones habituales del sistema (en Windows
`C:/Program Files/R`). Si lo instalas o cambias de ruta, pulsa **Volver a detectar**
sin cerrar la aplicación. La ruta elegida se guarda en `entorno_r.json`, en la carpeta
de configuración de la aplicación.

Los CSV y otros textos delimitados se leen con Python. Para Excel se necesitan
los paquetes R `readxl` y `jsonlite`; para SPSS, Stata y SAS, `haven` y `jsonlite`.
Los análisis requieren los paquetes R que utilice el código generado.

## Endpoints y privacidad

Configura proveedor, URL y modelo en **Endpoints IA** y usa **Probar conexión**.
Los valores iniciales son **64000 tokens** de salida y **300 segundos (5 minutos)**
de tiempo por operación; ambos son editables. El límite efectivo de salida
depende también del modelo y del servidor.
Los nombres de modelo son editables y dependen de lo que permita el proveedor.
El razonamiento está desactivado con presupuesto fijo **0**, tanto en el chat
como en las peticiones de prueba. Se solicita `reasoning_effort: none` en OpenAI,
`thinking: disabled` en DeepSeek y Anthropic, y `thinkingBudget: 0` en Gemini.
En llama-server se envían presupuesto cero, esfuerzo `none` y
`enable_thinking: false`. Los modelos clásicos sin modo de razonamiento no
reciben parámetros innecesarios. Sonnet 5.5 usa `between_tools` sin herramientas.
Los modelos conocidos que exigen razonamiento se rechazan al guardar o utilizar
el endpoint. Si el proveedor rechaza la desactivación, no se activa como alternativa;
si informa de tokens o bloques de pensamiento, la respuesta se rechaza.
Un servidor que omite esa información no permite verificar el consumo interno.
Consulta los parámetros oficiales de [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/),
[Anthropic](https://platform.claude.com/docs/en/build-with-claude/thinking)
y [Gemini](https://cloud.google.com/vertex-ai/generative-ai/docs/thinking).

Las claves se guardan mediante el gestor de credenciales disponible o DPAPI
en Windows. En otros sistemas, sin gestor de credenciales, se usa Fernet y
la variable `ANALISISR_MASTER_KEY`.

Los perfiles y bloqueos tienen almacenamiento propio: `%APPDATA%/AnalisisR`
en Windows, `~/Library/Application Support/AnalisisR` en macOS y
`$XDG_CONFIG_HOME/AnalisisR` (o `~/.config/AnalisisR`) en Linux.
No se leen ni migran perfiles de otras aplicaciones: configura tus endpoints en
AnalisisR. También se aceptan las variables de clave del proveedor
o `ANALISISR_API_KEY`.

Al aplicar el tratamiento, los niveles de medida declarados se guardan en un archivo
`<datos>.analisisr.json` junto al archivo de datos y se recuperan automáticamente al
volver a importarlo, de modo que solo hay que redefinir los tipos una vez. Las variables
marcadas como binarias se recodifican a 0 y 1 en la copia de trabajo, tomando su primera
categoría como 0 y referencia, con las etiquetas de valor reasignadas a los códigos nuevos
y la correspondencia anotada en el registro. En las plantillas de regresión, ANCOVA,
supervivencia, moderación y modelo multinivel las variables nominales entran como variables
indicadoras (contrastes de tratamiento) con su primera categoría como referencia, y el
efecto de la variable completa se contrasta con sus k-1 indicadoras a la vez.

Las transformaciones se aplican a copias en la carpeta temporal de sesión.
Todos los temporales se crean dentro de la carpeta del programa, en
`temporales/` (por defecto `C:\AnalisisR\temporales` en la versión instalada).
Los procesos R heredan esa ubicación. La carpeta de instalación debe permitir
escritura para poder ejecutar los análisis.
Al finalizar cada operación se conservan los archivos de sesión en memoria y
se elimina su carpeta temporal, también si hay error o cancelación. Se crean
de nuevo solo durante la siguiente operación o al guardar una sesión; los
scripts siguen disponibles para mostrar código y exportar a Word. Al cerrar,
se detiene el proceso activo, se borran los archivos propios que queden y se
descarta la memoria. Guarda una sesión o un informe antes de salir para conservarlos.
La limpieza afecta a las carpetas creadas por esta instancia; no recorre otras
sesiones ni borra archivos originales o informes guardados. Si una carpeta
está bloqueada o la sesión supera 1 GiB/10000 archivos en memoria, se informa
del fallo de limpieza sin descartar la copia de trabajo.

El endpoint recibe el diccionario sin filas y la conversación. La ejecución de R
está marcada por defecto y puedes desactivarla. La casilla independiente para
enviar la salida R al endpoint también está marcada por defecto: desmárcala
si quieres mantener los resultados locales. Las salidas pueden contener valores
de los datos y se envían al endpoint seleccionado para su interpretación. R se ejecuta con
los permisos del usuario; el filtro de operaciones no es un aislamiento de seguridad.

## Sesiones, informes y herramientas

- **Archivo → Guardar sesión** (`Ctrl+S`) crea un archivo portable `.analisisr`
  con la copia del origen, los datos tratados, las reglas y selección pendientes,
  la conversación, los scripts y las salidas. No incluye las claves del endpoint.
- **Archivo → Abrir sesión** (`Ctrl+O`) restaura una copia de trabajo independiente.
  Se mantienen el endpoint actual y las preferencias actuales de ejecutar R y
  enviar su salida. Los archivos guardados pueden contener datos
  sensibles. Límite por sesión: 1 GiB y 10000 archivos.
- **Archivo → Exportar informe a Word** (`Ctrl+Shift+E`) guarda preguntas,
  interpretación, tablas editables y el código R disponible en un `.docx`.
  También está disponible el botón **Exportar a Word** en Chat y R.
- **Ayuda → Diagnóstico de R y paquetes** comprueba versión, bibliotecas y paquetes
  recomendados sin instalar nada ni conectarse a la red.
  Incluye `lavaan`, `semTools`, `lavaangui`, `coefficientalpha`, `misty` y `mice`,
  con su versión si están disponibles o el estado «No instalado» si faltan.
- **Usar plantilla**, en Chat y R, abre un formulario para seleccionar variables
  reales. Inserta sus nombres sin comillas y separados por comas; no envía la
  consulta automáticamente ni deja campos pendientes entre corchetes.
  Incluye **Diferencia entre medias** para dos grupos independientes, **ANOVA**
  de un factor y **Tablas de contingencia** con frecuencias, porcentajes y asociación.
  Las veintisiete plantillas, ordenadas alfabéticamente, detallan estimandos, pruebas, diagnósticos, tamaños de efecto
  e interpretación. **Regresión** solicita un modelo lineal con Breusch–Pagan,
  inferencia robusta HC3, VIF/GVIF, índices de condición, Shapiro–Wilk de residuos,
  RESET e influencia; para una respuesta no continua pide aclarar el modelo.
  Se documentan ausentes, métodos no estimables y paquetes que falten. La
  interpretación se limita a resultados calculados; si no se comparten con la IA,
  se solicita que el propio R construya el resumen interpretativo local.
  Las diez últimas amplían el alcance a modelos de medida y diseños complejos:
  **Análisis factorial confirmatorio** e **Invarianza de medida** con lavaan y semTools, donde
  defines en el formulario tantas variables latentes como necesites con sus indicadores; con dos o
  más latentes el modelo las deja correlacionadas y añade validez discriminante con Fornell-Larcker,
  matrices HTMT y HTMT2 con intervalos de confianza por bootstrap y el contraste del modelo con la
  correlación fijada a uno,
  **Mediación** con IC bootstrap y **Moderación** con pendientes simples, **ANOVA de medidas
  repetidas** con afex y correcciones de esfericidad, **Modelo multinivel** con lme4,
  **Curva ROC y capacidad diagnóstica** con pROC, **Análisis de supervivencia** con survival,
  **Ausentes e imputación múltiple** con mice y misty, y **Acuerdo entre evaluaciones** con
  coeficientes intraclase, kappa y error típico de medida.
  Incluyen **Análisis factorial exploratorio**, **Regresión logística**,
  **Análisis clúster**, **Análisis discriminante** y **Consistencia interna**.
  Esta última solicita alfa bruto, estandarizado y ordinal, omega en escalas
  explícitas y cambios al eliminar ítems, manteniendo la muestra y documentando
  los modelos que no puedan estimarse.
  **Fiabilidad** y **Consistencia interna** emplean `coefficientalpha` para alfa
  y omega sobre puntuaciones observadas, en versiones brutas y estandarizadas,
  con errores estándar, IC y contrastes de tau-equivalencia/homogeneidad. Se
  declara `varphi` y la política de ausentes; las eliminaciones de ítems actúan
  sobre columnas. Los coeficientes ordinales usan métodos complementarios
  explícitos. El diagnóstico de R comprueba si `coefficientalpha` está instalado.
  Referencia: [manual de coefficientalpha](https://cran.r-project.org/web/packages/coefficientalpha/refman/coefficientalpha.html).
  **ANCOVA** selecciona respuesta, grupo y covariables y solicita interacciones,
  medias ajustadas y contrastes. **Regresión ordinal** exige un orden explícito
  y evalúa odds proporcionales; **Regresión multinomial** declara la referencia
  y los contrastes por categoría. **Regresión para recuentos** evalúa Poisson
  y binomial negativa; permite seleccionar una exposición opcional para el
  offset y distingue razones de tasas de razones de recuentos esperados.
- **@** en la consulta abre una lista emergente con selección múltiple e inserta
  las variables elegidas en la posición del cursor, separadas por comas.
- **Abrir reciente**, en Datos, permite seleccionar los últimos cinco archivos
  importados correctamente. La lista se conserva entre aperturas de la aplicación.
- Los descriptivos disponen de un resumidor local de columnas que distingue los
  datos numéricos de los categóricos, sin forzar conversiones de categorías.
- Antes de ejecutar se comprueba localmente la sintaxis del código generado.
  Si falla, se solicitan correcciones, con un máximo de tres errores sintácticos consecutivos.
  El diagnóstico del analizador no evalúa el código ni contiene salidas de los
  datos, por lo que puede corregirse aunque compartir la salida esté desactivado.
  Los errores que aparecen después de ejecutar siguen sujetos a ese consentimiento.
- Los análisis admiten hasta seis propuestas de código R y tres consultas de ayuda
  independientes por turno, seguidas de una respuesta final sin ejecución. Cada
  bloque R parte de una sesión nueva y debe ser autocontenido. Si la IA no cierra
  el análisis, se muestran los resultados ya obtenidos y el último diagnóstico,
  indicando que está incompleto.
- Cada consulta incorpora automáticamente la instrucción de presentar los
  resultados en tablas. Las salidas correctas de R sin estructura tabular se
  conservan en una tabla de una columna; los errores se muestran como diagnósticos.
- El chat y Word convierten la notación LaTeX estadística habitual a símbolos
  legibles: letras griegas, hipótesis, desigualdades, potencias, fracciones y raíces.
  Se conserva el código literalmente. Las estructuras LaTeX no compatibles se
  mantienen para evitar alterar el significado; no se requiere instalar un motor TeX.

El logotipo y los iconos están en `assets/analisisr-logo.png`,
`assets/analisisr-icon.png` y `assets/analisisr.ico`.

## Desarrollo y pruebas

- `AnalisisR.py`: ventana, conversación y protocolo de trabajadores JSON.
- `analisisr_core.py`: importación, perfiles, recodificación, proveedores y R del sistema.
- `analisisr_ui.py`: widgets, Markdown y procesos Qt cancelables.
- `analisisr_secrets.py`: perfiles cifrados propios.
- `analisisr_session.py`: sesiones portables y validación de archivos.
- `analisisr_docx.py`: exportación Word sin dependencias externas.
- `tests/`: regresiones con datos sintéticos y endpoints simulados.

```powershell
python -m pip install pytest python-docx
python -m pytest -q
```

Las pruebas de R y Qt se omiten si falta su dependencia. Las pruebas de
independencia copian los módulos a una carpeta aislada y comprueban que no se cargue
código de fuera de ese directorio. Ninguna prueba necesita claves reales ni un endpoint
remoto.

## Compilar para otros sistemas

```bash
python -m PyInstaller --noconfirm AnalisisR_multiplataforma.spec
```

`AnalisisR_multiplataforma.spec` compila sin protección y sin R en Windows, Linux y macOS
(hay que compilar en el sistema de destino: PyInstaller no cruza plataformas). Las
dependencias por sistema, las notas de Qt en Linux, el empaquetado en macOS y cómo
comprobar el resultado están en [BUILD.md](BUILD.md).

## Compilación protegida y despliegue en Windows

Entorno comprobado: Python 3.11 de 64 bits, PyInstaller 6.15.0 y PyArmor 9.2.7
con licencia Pro. La compilación ya no necesita R: el equipo de destino aporta el suyo.
PyArmor puede necesitar conexión para verificar su licencia.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\compilar.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\compilar.ps1 -Desplegar
```

`AnalisisR_onedir.spec` ejecuta PyArmor sobre los seis módulos y genera
`dist/AnalisisR/`: `AnalisisR.exe`, `AnalisisRWorker.exe` y `_internal/` con
Python/Qt/recursos. **Nunca se incluye R portable**: el paquete ocupa unos 120 MB y
usa el R del equipo donde se ejecuta. Se comprueba que todos los módulos propios se
empaquetan ofuscados; si falla PyArmor se detiene la compilación. No se incluyen
claves, perfiles personales ni modelos IA. El equipo de destino no necesita instalar
Python, pero sí R 4.x con los paquetes del diagnóstico; los endpoints se configuran
desde la aplicación y la guía se abre con F1. Conserva toda la carpeta onedir.

`tools/validar_paquete.py` comprueba protección, interfaz, paquetes R, alfa/omega,
importación CSV/Excel/SPSS y ubicación de temporales usando un entorno aislado.
Comprueba además que el paquete no contiene R y que la detección encuentra el del
sistema sin `R_HOME` ni `PATH`, por lo que debe ejecutarse en un equipo con R.
`desplegar.ps1` instala solo un paquete validado; prepara la copia antes de
sustituir el destino y conserva la instalación anterior como respaldo. Cierra
la aplicación antes de actualizar. El destino predeterminado es `C:\AnalisisR`.

Las sesiones guardadas en otra unidad usan un nombre nuevo para conservar
cualquier archivo anterior sin crear temporales fuera de la instalación.
