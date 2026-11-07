"""AnalizaR Desktop: datos, endpoints y procedimientos estadísticos conversacionales con R.

Ejecutar: C:/Users/Eulogio/anaconda3/python.exe AnalisisR.py
Aplicación independiente con módulos propios situados junto a este archivo.
"""
from __future__ import annotations

import csv
import json
import time as _time
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

import analisisr_core as engine
import analisisr_secrets as secrets
from analisisr_session import SessionWorkspace, configure_temporaries, temporary_file, replace_file

VERSION = "1.0"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
RESULT_FORMAT = "Presentar los resultados obtenidos con formato de tabla de Word: tablas Markdown con encabezados y separadores, sin bloques de consola para los resultados."
MARKDOWN_TABLE = re.compile(r"^\|[^\n]*\|[ \t]*\n\|(?:[ \t]*:?-{3,}:?[ \t]*\|)+[ \t]*$", re.M)
TEMPLATES = {
    "ANCOVA": (
        "Compara [puntuación] entre los niveles de [grupo] ajustando por [covariables] mediante "
        "ANCOVA con stats::lm. Exige respuesta y covariables cuantitativas, factor con al menos dos "
        "niveles observados y observaciones independientes según el diseño. Presenta n, descriptivos "
        "por grupo, ausentes y distribución de covariables; comprueba solapamiento de sus rangos "
        "entre grupos para evitar extrapolaciones. Declara fórmula y codificación; centra covariables "
        "en valores explícitos y conserva las unidades. Ajusta primero un modelo con interacciones "
        "grupo×cada covariable y contrasta conjuntamente la homogeneidad de pendientes mediante F "
        "parcial frente al modelo aditivo sobre los mismos casos completos. Informa modelos comparados, "
        "F, grados de libertad y p; no interpretes falta de significación como prueba de pendientes "
        "idénticas. Si las interacciones son relevantes, mantenlas e interpreta efectos de grupo y "
        "pendientes simples en valores de covariables justificados y dentro del soporte común; "
        "no presentes una diferencia ajustada única como constante. En un modelo aditivo defendible, "
        "contrasta el efecto global de grupo ajustado por covariables comparándolo con el modelo "
        "sin grupo mediante F parcial. Evalúa linealidad, normalidad de residuos con Shapiro–Wilk "
        "cuando sea aplicable, heterocedasticidad con Breusch–Pagan y observaciones influyentes con "
        "residuos studentizados, leverage y Cook. Ante heterocedasticidad añade inferencia HC3 con "
        "sandwich y lmtest, usando una prueba conjunta robusta para el efecto global e IC robustos "
        "para contrastes, claramente separados de los clásicos. Calcula medias marginales ajustadas "
        "y diferencias por pares con emmeans, IC del 95 % y ajuste de Tukey para la familia de "
        "comparaciones; especifica valores de covariables y ponderaciones de la rejilla de referencia. "
        "Presenta B, errores estándar, IC, p y R² ajustado; informa eta cuadrado parcial del efecto "
        "de grupo solo para el contraste clásico correspondiente, sin atribuirlo al robusto. "
        "Interpreta medias y diferencias ajustadas, pendiente e interacciones en unidades originales. "
        "Advierte que ajustar por covariables no elimina por sí solo confusión y que covariables "
        "posteriores al tratamiento requieren justificación; no atribuyas causalidad automáticamente."
    ),
    "Regresión ordinal": (
        "Modela [respuesta] según [predictores] mediante regresión logística ordinal acumulativa "
        "con ordinal::clm, link='logit'. Exige al menos tres categorías ordenadas y declara su orden "
        "sustantivo: utiliza metadatos explícitos o solicita confirmación, nunca lo deduzcas del "
        "orden alfabético. No trates códigos ordinales como una respuesta continua. Informa n válido, "
        "frecuencias por categoría, ausentes, referencias de predictores, fórmula y número de parámetros. "
        "Comprueba celdas escasas, rango de la matriz de diseño, colinealidad, convergencia, gradiente, "
        "Hessiano y posibles problemas de separación; no presentes coeficientes o IC inestables como "
        "fiables. Explicita la parametrización logit P(Y≤j)=umbral_j−Xβ; interpreta exp(β) como razón "
        "de odds acumulativas de estar por encima de cada umbral frente a estar en él o por debajo. "
        "Presenta B, error estándar, z de Wald, p, OR acumulativa ajustada e IC del 95 % con método "
        "de perfil o Wald identificado; muestra los umbrales por separado y no los interpretes como "
        "efectos de predictores. Contrasta odds proporcionales con ordinal::nominal_test mediante "
        "razón de verosimilitudes e informa estadísticos, grados de libertad y p por término; "
        "considera ordinal::scale_test para heterogeneidad de escala, distinguiendo ambas hipótesis. "
        "Ante incumplimiento, justifica un modelo de odds parcialmente proporcionales mediante nominal "
        "o un modelo alternativo identificable, sin cambiar silenciosamente el estimando ni imponer "
        "un OR común. Evalúa forma funcional de predictores continuos mediante alternativas flexibles "
        "comparables por verosimilitud cuando n lo permita; no exijas normalidad ni homocedasticidad "
        "de residuos gaussianos. Presenta contraste global frente al modelo nulo, log-verosimilitud, "
        "AIC y pseudo-R² de McFadden, sin llamarlo porcentaje de varianza explicada. Calcula "
        "probabilidades predichas de cada categoría para perfiles definidos dentro del rango observado, "
        "comprobando que sumen uno. Separa evaluación aparente de validación cruzada estratificada con "
        "semilla, pliegues compatibles con categorías escasas y preprocesamiento dentro del pliegue; "
        "informa matriz de confusión, sensibilidad por categoría y ranked probability score, "
        "o explica qué no es estimable. Interpreta dirección hacia categorías superiores o inferiores, "
        "magnitud, precisión y adecuación del supuesto proporcional, sin causalidad ni umbrales de "
        "decisión elegidos en los mismos datos de evaluación."
    ),
    "Regresión multinomial": (
        "Modela [respuesta] a partir de [predictores] mediante regresión logística multinomial "
        "nominal con nnet::multinom, Hess=TRUE. Exige al menos tres categorías no ordenadas y "
        "confirma la categoría de referencia antes de ajustar si no está definida en los metadatos; "
        "no la selecciones silenciosamente por frecuencia u orden alfabético. Presenta n válido, "
        "frecuencias por categoría, ausentes, referencias de factores, fórmula y parámetros estimados. "
        "Evalúa categorías y combinaciones escasas, número de casos por parámetro, rango y "
        "colinealidad del diseño, separación, convergencia y condicionamiento del Hessiano. Si "
        "reescalas predictores para estabilidad numérica, declara la transformación y devuelve "
        "coeficientes interpretables en unidades explícitas. Para cada categoría frente a la "
        "referencia presenta B, error estándar, z de Wald, p y exp(B) con IC del 95 %, identificando "
        "el método y la incertidumbre de estimaciones inestables. Explica exp(B) como cambio "
        "multiplicativo de P(Y=categoría)/P(Y=referencia) por unidad del predictor manteniendo "
        "los demás constantes; no lo confundas con riesgo relativo marginal ni con cambio absoluto "
        "de probabilidad. Contrasta globalmente el modelo y cada predictor mediante razón de "
        "verosimilitudes sobre modelos anidados ajustados a exactamente los mismos casos, "
        "informando X², grados de libertad y p; distingue estos contrastes de los Wald por "
        "coeficiente. Informa log-verosimilitud, devianza, AIC y pseudo-R² de McFadden. Discute "
        "el supuesto de independencia de alternativas irrelevantes según el contexto; si se "
        "realiza Hausman–McFadden con una implementación compatible, identifica modelos y "
        "restricciones, y no interpretes un estadístico negativo o una prueba no estimable como "
        "cumplimiento. No apliques el supuesto de odds proporcionales ni normalidad de residuos "
        "gaussianos a este modelo. Presenta probabilidades por categoría para perfiles relevantes "
        "con suma uno. Evalúa log-loss multiclase, Brier multiclase con definición explícita, "
        "matriz de confusión, sensibilidad por clase y exactitud balanceada, separando ajuste "
        "aparente y validación cruzada estratificada con semilla y sin fuga de datos. Interpreta "
        "contrastes respecto a la referencia y probabilidades, teniendo en cuenta desequilibrio "
        "de clases, precisión y límites del diseño; no atribuyas causalidad ni interpretes un "
        "buen ajuste aparente como validación predictiva."
    ),
    "Regresión para recuentos": (
        "Modela [respuesta] a partir de [predictores] mediante regresión para recuentos. Exposición "
        "seleccionada: [exposición]. Exige respuesta entera no negativa; informa n, ausentes, "
        "media, varianza, rango y proporción de ceros. Si hay exposición, verifica que sea "
        "cuantitativa, finita y estrictamente positiva, declara sus unidades e incluye "
        "offset(log(exposición)) con coeficiente fijo 1. Si no está especificada, modela recuentos "
        "y no inventes un tiempo de seguimiento ni interpretes el resultado como tasa. Ajusta "
        "Poisson con stats::glm, family=poisson(link='log'), declarando fórmula, referencias, "
        "parámetros, convergencia, rango y posibles estimaciones de frontera. Evalúa dispersión "
        "mediante suma de residuos de Pearson al cuadrado dividida por grados de libertad "
        "residuales, sin tratar la razón como un p; añade AER::dispersiontest cuando esté "
        "disponible, explicando hipótesis, alternativa y forma de la relación media-varianza. "
        "Ante sobredispersión considera binomial negativa con MASS::glm.nb (varianza=μ+μ²/θ), "
        "informando θ, su incertidumbre y convergencia. Compara AIC y ajuste sobre los mismos "
        "casos y respuesta; no apliques sin justificación un contraste chi-cuadrado ordinario "
        "Poisson frente a binomial negativa, pues el parámetro adicional está en la frontera. "
        "Si utilizas quasi-Poisson como sensibilidad, aclara que no proporciona una verosimilitud "
        "completa ni AIC comparable. Evalúa residuos simulados con DHARMa cuando esté instalado, "
        "dispersión, valores influyentes y ceros observados frente a los predichos; no selecciones "
        "un modelo de ceros inflados solo por una proporción alta de ceros sin comparar con el "
        "modelo ajustado y justificar el mecanismo generador. No exijas Shapiro–Wilk ni "
        "homocedasticidad gaussiana. Presenta B, errores estándar, z o t según el estimador, "
        "p e IC del 95 %, exp(B), devianza y grados de libertad cuando proceda. Interpreta "
        "exp(B) como razón de tasas con exposición y como razón de recuentos esperados sin ella, "
        "manteniendo los demás predictores constantes. Informa contrastes globales y por término "
        "con inferencia compatible con el modelo, y predicciones de medias o tasas para perfiles "
        "con unidades explícitas e IC de la media, sin confundirlos con intervalos predictivos "
        "individuales. Examina independencia según el diseño; si hay medidas repetidas o "
        "agrupamiento, solicita definir esa estructura antes de asumir independencia. Interpreta "
        "magnitud, precisión, adecuación de la dispersión y limitaciones, sin atribuir causalidad."
    ),
    "Análisis clúster": (
        "Identifica perfiles de observaciones mediante análisis clúster de [variables], sin variable "
        "dependiente ni grupos predefinidos. Comprueba escalas, ausentes, variables constantes, duplicados "
        "y valores extremos; excluye identificadores y no conviertas categorías nominales en números. "
        "Para variables cuantitativas utiliza distancia euclídea tras estandarización z, informa medias "
        "y desviaciones usadas y ajusta agrupamiento jerárquico con stats::hclust, method=ward.D2; "
        "contrasta la solución con stats::kmeans, nstart=50 y semilla fija. Para datos mixtos u ordinales "
        "justifica distancia de Gower con cluster::daisy y PAM con cluster::pam; declara ordinalidad, "
        "ponderaciones y tratamiento de ausentes. No apliques Ward a una disimilitud no euclídea ni "
        "k-means a códigos nominales. Compara k desde 2 hasta min(10,n-1), limitado por observaciones "
        "distintas, con anchura de silueta media y por grupo (cluster::silhouette), tamaños y casos "
        "con silueta negativa. Para la rama cuantitativa añade estadístico gap con cluster::clusGap, "
        "100 réplicas, semilla fija y regla de un error estándar, incluyendo la posibilidad k=1; "
        "no fuerces varios grupos si no hay estructura defendible. Evalúa estabilidad por remuestreo "
        "si es computacionalmente viable (fpc::clusterboot, 100 réplicas), indicando algoritmo y "
        "similitud de Jaccard por clúster; si no es viable, declara la limitación. Informa distancia, "
        "escalado, algoritmo, criterio de k, convergencia, tamaños, centroides o medoides y perfiles "
        "en unidades originales. Resume asignaciones por índice de fila y casos ambiguos sin divulgar "
        "identificadores. Interpreta grupos como solución exploratoria dependiente de esas decisiones, "
        "no como clases naturales demostradas; no uses contrastes de las mismas variables de formación "
        "como validación independiente ni atribuyas significación a diferencias construidas por el algoritmo."
    ),
    "Análisis discriminante": (
        "Realiza análisis discriminante para clasificar los grupos conocidos de [respuesta] a partir "
        "de [predictores]. Exige respuesta categórica con al menos dos grupos y predictores cuantitativos; "
        "informa tamaños por grupo, ausentes, número de predictores, constantes, colinealidad y rango "
        "de las matrices de covarianza intragrupo. No conviertas predictores nominales en cantidades "
        "sin justificar un modelo alternativo. Ajusta análisis discriminante lineal con MASS::lda, "
        "declarando probabilidades a priori y costes de clasificación; usa proporciones muestrales "
        "solo como supuesto explícito si no hay probabilidades poblacionales conocidas. Evalúa "
        "normalidad multivariante intragrupo mediante Mardia cuando n y rango lo permitan, y homogeneidad "
        "de covarianzas con Box M (biotools::boxM), informando estadístico, grados de libertad, p "
        "y sensibilidad a no normalidad y tamaños desiguales. No selecciones LDA o QDA solo por Box M; "
        "considera MASS::qda como sensibilidad únicamente con covarianzas estimables y tamaño suficiente "
        "en cada grupo. Presenta hasta min(p,g-1) funciones: autovalores, correlaciones canónicas, "
        "coeficientes estandarizados, matriz de estructura y centroides, indicando su definición y "
        "escala. Para contraste global de diferencias multivariantes utiliza lambda de Wilks con "
        "aproximación F y grados de libertad cuando sea estimable (stats::manova); no inventes "
        "contrastes secuenciales de raíces que el ajuste no proporcione. Evalúa clasificación mediante "
        "validación cruzada estratificada con semilla y número de pliegues compatible con el grupo "
        "menor; ajusta todo preprocesamiento y el modelo dentro de cada pliegue, sin fuga de datos. "
        "Separa matriz de confusión aparente de la validada; informa exactitud, exactitud balanceada, "
        "sensibilidad por clase y comparación con clasificar siempre al grupo mayoritario. Interpreta "
        "separación, contribuciones, errores e incertidumbre sin confundir discriminación aparente "
        "con generalización ni coeficientes con efectos causales."
    ),
    "Análisis factorial exploratorio": (
        "Realiza un análisis factorial exploratorio de [variables] para investigar factores comunes, "
        "no componentes principales. Comprueba al menos tres indicadores, escalas, categorías, n "
        "efectivo, ausentes, constantes y correlaciones casi perfectas. Para indicadores continuos "
        "usa Pearson; para ordinales justifica correlaciones policóricas (tetracóricas si son "
        "dicotómicos) con psych, declarando niveles y categorías escasas. Comprueba que la matriz "
        "sea definida positiva; no la suavices ni imputes sin explicitar la decisión. Informa KMO "
        "global y MSA por indicador (psych::KMO), y esfericidad de Bartlett (psych::cortest.bartlett) "
        "con X², grados de libertad, p y limitaciones de la aproximación para matrices policóricas. "
        "Determina el número de factores mediante análisis paralelo de factores comunes "
        "(psych::fa.parallel, fa='fa', fm='minres', 200 réplicas, semilla fija y matriz acorde a la "
        "escala), junto con autovalores, sedimentación e interpretabilidad; no uses solo autovalores "
        "mayores que 1 ni fuerces factores si el paralelo sugiere cero. Extrae por mínimos residuos "
        "(psych::fa, fm='minres') y rotación oblicua oblimin cuando haya más de un factor. Declara "
        "la identificación y suficiencia muestral sin aplicar una regla sujetos/ítem como garantía. "
        "Presenta matrices de patrón y estructura diferenciadas, correlaciones factoriales, "
        "comunalidades, unicidades y varianza explicada, sin sumar como independientes factores "
        "correlacionados. Identifica cargas débiles, cargas cruzadas, casos Heywood, falta de "
        "convergencia y factores poco definidos; usa puntos de corte solo como criterios orientativos "
        "declarados, sin eliminar indicadores automáticamente. Informa RMSR y, cuando sean válidos "
        "y estén disponibles, RMSEA con IC, TLI y contraste de ajuste, identificando método y "
        "limitaciones para datos ordinales. Interpreta factores por contenido de indicadores sin "
        "inventar etiquetas sustantivas; distingue exploración de confirmación y recomienda "
        "replicación independiente antes de afirmar estructura estable."
    ),
    "Consistencia interna": (
        "Evalúa exhaustivamente la consistencia interna de [ítems]. Confirma el constructo, sentido "
        "de puntuación, rango teórico y carácter continuo u ordinal; no adivines ítems inversos ni "
        "los inviertas automáticamente por correlación negativa. Si faltan claves, solicita aclararlas. "
        "Describe categorías observadas, frecuencias, efectos suelo/techo, ausentes y n usado. "
        "Declara el tratamiento de incompletos y conserva la misma muestra para comparar versiones "
        "con y sin ítems; no imputes ni uses eliminación por pares silenciosamente. Calcula alfa "
        "de Cronbach bruto sobre covarianzas y alfa estandarizado sobre correlaciones de Pearson "
        "con coefficientalpha::alpha, con IC del 95 % y método explícito. Para ítems ordinales "
        "estima matriz policórica o tetracórica y alfa ordinal, diferenciándolo de alfa sobre "
        "puntuaciones observadas; comprueba categorías escasas, matriz definida positiva y "
        "estimabilidad. Evalúa dimensionalidad mediante análisis paralelo de factores comunes; "
        "no fuerces un modelo unidimensional por un alfa elevado. Bajo un modelo factorial "
        "defendible e identificado estima omega total para la suma de puntuaciones brutas y "
        "omega total para la suma de ítems estandarizados, especificando matriz, cargas, "
        "varianzas de error y ponderaciones; no llames estandarizado al mismo coeficiente duplicado. "
        "Para ordinales usa un modelo categórico apropiado (lavaan con WLSMV y ordered, si está "
        "instalado) y semTools::compRelSEM, distinguiendo fiabilidad en escala observada ordinal "
        "de la respuesta continua latente (ord.scale=TRUE y FALSE, respectivamente). Para las "
        "versiones estandarizadas define explícitamente las ponderaciones y la escala de cada ítem, "
        "sin confundir estandarizar ítems con fijar la varianza del factor. No presentes omega "
        "basado en correlaciones policóricas como fiabilidad automática de la suma observada. "
        "Omega jerárquico solo si existe un modelo con factor general identificable; si no, "
        "declara que no procede. Presenta una tabla por ítem con correlación ítem-resto corregida, "
        "alfa bruto, estandarizado y ordinal al eliminarlo, omega total bruto y estandarizado "
        "al eliminarlo, y cambios respecto a la escala completa. Reajusta el mismo tipo de modelo "
        "en cada eliminación; si pierde identificación o convergencia, marca no estimable, "
        "sin reutilizar el omega inicial. Añade IC de omega mediante bootstrap de personas "
        "con semilla fija y 1000 réplicas si es viable, manteniendo claves y modelo, e informa "
        "réplicas fallidas y método; no inventes IC cuando no pueda estimarse. Usa coefficientalpha "
        "para alfa y omega de puntuaciones observadas, psych para análisis paralelo y policóricas, "
        "y lavaan/semTools para fiabilidad ordinal según disponibilidad. Interpreta magnitud, precisión, dimensionalidad, "
        "redundancia y cobertura del constructo; un aumento al eliminar un ítem no justifica "
        "por sí solo su supresión. No equipares consistencia interna con validez, estabilidad "
        "temporal o unidimensionalidad, ni apliques 0,70 como umbral universal."
    ),
    "Regresión logística": (
        "Ajusta una regresión logística binaria de [respuesta] sobre [predictores] con intercepto "
        "y efectos principales (stats::glm, family=binomial(link='logit')). Exige exactamente dos "
        "categorías observadas: si la codificación es 0/1 define 1 como evento; en otra codificación "
        "solicita confirmar evento y referencia antes de ajustar. No conviertas automáticamente "
        "una respuesta multinomial u ordinal en binaria. Declara fórmula, referencias de factores, "
        "n inicial y válido, eventos y no eventos, parámetros estimados y riesgo de sobreajuste. "
        "Comprueba convergencia, rango, observaciones influyentes y separación completa o cuasicompleta; "
        "si existe separación, explica por qué la máxima verosimilitud puede no ser finita y "
        "propón estimación de Firth (logistf) o reducción de sesgo (brglm2) si están instalados, "
        "identificando el cambio de método y sin publicar OR infinitas como fiables. Presenta "
        "coeficientes logit B, errores estándar, z de Wald, p, OR ajustadas exp(B) e IC del 95 %, "
        "indicando si el IC es de perfil o Wald y usando inferencia compatible con el estimador. "
        "Contrasta el modelo frente al nulo por razón de verosimilitudes, con devianza, grados "
        "de libertad y p; informa log-verosimilitud, AIC y pseudo-R² de McFadden, sin interpretarlo "
        "como varianza explicada de regresión lineal. Evalúa colinealidad con car::vif, diferenciando "
        "VIF y GVIF ajustado por dimensión. Evalúa linealidad en el logit de predictores continuos "
        "comparando términos lineales con splines naturales mediante razón de verosimilitudes "
        "cuando haya información suficiente; no exijas normalidad ni homocedasticidad de residuos "
        "gaussianos. Evalúa influencia mediante residuos de devianza, leverage y Cook sin borrar "
        "casos automáticamente. Evalúa discriminación con ROC/AUC e IC (pROC, evento y dirección "
        "explícitos), calibración con intercepto y pendiente y puntuación de Brier, distinguiendo "
        "evaluación aparente y validación cruzada estratificada con semilla; todo preprocesamiento "
        "debe aprenderse dentro de cada pliegue. Presenta matriz de confusión, sensibilidad, "
        "especificidad y valores predictivos a umbral 0,5 declarado como provisional; no optimices "
        "el umbral en los mismos datos de evaluación ni ocultes el desequilibrio de clases. "
        "Si usas Hosmer–Lemeshow, informa agrupación y limitaciones; no lo uses como única "
        "evaluación de calibración. Interpreta OR por unidad y categoría de referencia, "
        "manteniendo constantes los demás predictores; distingue odds de probabilidad y riesgo, "
        "explica incertidumbre y no atribuyas causalidad ni generalización a un buen ajuste aparente."
    ),
    "Descriptivos": (
        "Realiza un análisis descriptivo de [variables] por [grupo]. Distingue variables cuantitativas, "
        "ordinales y nominales según sus clases y metadatos; no conviertas códigos de categorías en medidas continuas. "
        "Para cada variable cuantitativa calcula n válido, n y porcentaje de ausentes, media, desviación estándar "
        "muestral, IC del 95 % de la media mediante t de Student cuando sea estimable, mediana, Q1, Q3, "
        "rango intercuartílico, mínimo y máximo. Cuenta posibles valores atípicos mediante cercas de Tukey "
        "de 1,5 rangos intercuartílicos, sin eliminarlos. Para variables categóricas presenta frecuencias "
        "absolutas y porcentajes sobre casos válidos, incluyendo niveles sin observaciones cuando estén definidos. "
        "Si hay agrupación, desglosa por nivel y presenta también el total. Usa descriptivos() para el resumen "
        "numérico básico y amplíalo con stats; evita pruebas inferenciales de diferencias entre grupos. "
        "Interpreta tendencia central, dispersión, asimetría sugerida por los resúmenes y patrón de ausentes, "
        "sin afirmar normalidad a partir de estos indicadores. Señala muestras pequeñas y variables constantes."
    ),
    "Diferencia entre medias": (
        "Contrasta la igualdad de medias de [puntuación] entre los dos grupos independientes de [grupo]. "
        "Exige respuesta cuantitativa y exactamente dos niveles observados; explicita que la independencia "
        "depende del diseño. Presenta por grupo n, media, desviación estándar, mediana y rango intercuartílico. "
        "Define el orden de los grupos y estima la diferencia media grupo 1 menos grupo 2. Utiliza como "
        "contraste principal la t bilateral de Welch (stats::t.test, var.equal=FALSE): informa t, grados de "
        "libertad de Satterthwaite, p e IC del 95 % de la diferencia. Evalúa homogeneidad con Brown–Forsythe "
        "(car::leveneTest centrado en la mediana) escribiendo el grupo como factor explícito, es decir "
        "car::leveneTest(puntuación ~ factor(grupo), center = median): las variables binarias llegan "
        "recodificadas a 0 y 1, y con una columna numérica la prueba se detiene con el error Levene's "
        "test is not appropriate with quantitative explanatory variables. Evalúa también la "
        "normalidad con Shapiro–Wilk por grupo cuando sea aplicable; "
        "no selecciones Student o Welch únicamente por el p de homogeneidad ni cambies automáticamente de "
        "prueba por Shapiro. Calcula g de Hedges con IC del 95 %, indicando el estandarizador y su limitación "
        "ante varianzas desiguales. Si hay asimetría extrema o valores influyentes, justifica una sensibilidad "
        "robusta; si empleas Mann–Whitney, aclara que contrasta distribuciones/rangos y no la igualdad de "
        "medias ni, en general, medianas. Interpreta dirección, magnitud, precisión y relevancia sustantiva "
        "de la diferencia, distinguiendo evidencia insuficiente de equivalencia."
    ),
    "ANOVA": (
        "Analiza [puntuación] según el factor [grupo] mediante ANOVA de un factor entre sujetos. "
        "Exige respuesta cuantitativa y al menos dos niveles observados; verifica tamaños por grupo y "
        "advierte que la independencia se establece por diseño. Presenta n, media, desviación estándar e "
        "IC del 95 % por nivel. Ajusta el modelo de medias y evalúa normalidad de sus residuos con "
        "Shapiro–Wilk cuando sea aplicable, y homogeneidad mediante Brown–Forsythe "
        "(car::leveneTest, centro mediana), escribiendo el factor explícitamente como "
        "car::leveneTest(respuesta ~ factor(grupo), center = median), porque con una columna numérica "
        "la prueba se detiene con el error Levene's test is not appropriate with quantitative "
        "explanatory variables. Justifica ANOVA clásico con stats::aov o ANOVA de Welch con "
        "stats::oneway.test, var.equal=FALSE, atendiendo también al desequilibrio y la magnitud de la "
        "heterocedasticidad, sin decidir solo por un p de supuestos. Informa F, ambos grados de libertad "
        "y p. Para el clásico estima omega cuadrado e IC del 95 % si es estimable; para Welch no reutilices "
        "mecánicamente la fórmula clásica: identifica un estimador compatible o declara su ausencia. "
        "Con tres o más niveles realiza comparaciones post hoc: stats::TukeyHSD para el clásico o Games–Howell "
        "(rstatix::games_howell_test) "
        "para Welch, con diferencias dirigidas, IC simultáneos del 95 % y p ajustados; indica el método y "
        "la familia de comparaciones, sin duplicar ajustes. Si se usa Kruskal–Wallis como sensibilidad, "
        "explica el cambio de hipótesis a distribuciones/rangos. Interpreta contraste global, pares, "
        "magnitud y precisión, sin convertir ausencia de significación en igualdad."
    ),
    "Tablas de contingencia": (
        "Construye una tabla de contingencia con [filas] en las filas y [columnas] en las columnas. "
        "Trata ambas variables como categóricas, conserva etiquetas y excluye del contraste los casos "
        "incompletos, informando cuántos; no conviertas ausentes en una categoría sin autorización. "
        "Presenta frecuencias observadas y esperadas bajo independencia, totales y porcentajes por fila "
        "y por columna con denominadores explícitos. Elimina únicamente márgenes vacíos para el contraste "
        "y comprueba que queden al menos dos niveles por dimensión. Informa mínimo esperado y porcentaje "
        "de celdas con esperado menor que 5. Usa chi-cuadrado de Pearson sin corrección cuando no haya "
        "esperados menores que 1 y como máximo un 20 % sean menores que 5; si no, Fisher exacto cuando sea "
        "viable o una p Monte Carlo con semilla y 10000 réplicas, indicando el método y sus límites. "
        "Utiliza stats::chisq.test o stats::fisher.test. Informa X², grados de libertad y p cuando "
        "correspondan; Fisher no tiene un X² ni grados de libertad que deban inventarse. Calcula V de "
        "Cramér a partir del X² de Pearson y n válido aunque el p principal sea exacto, aclarando su base. "
        "En tablas 2×2 añade odds ratio e IC del 95 % con categorías de referencia y orientación explícitas. "
        "Si examinas celdas, presenta residuos estandarizados ajustados y p exploratorios ajustados por "
        "Holm. Interpreta patrón, intensidad e incertidumbre de la asociación, sin atribuir causalidad."
    ),
    "Antes y después": (
        "Compara [antes] y [después] como dos mediciones cuantitativas de las mismas personas, "
        "emparejadas por fila. Excluye solo pares incompletos e informa pares iniciales, válidos y perdidos. "
        "Define el cambio como después menos antes; presenta descriptivos de ambas medidas y de las "
        "diferencias individuales. Evalúa normalidad de las diferencias, no de cada medida por separado, "
        "mediante Shapiro–Wilk cuando sea aplicable, y revisa valores extremos sin eliminarlos automáticamente. "
        "Usa t bilateral para muestras relacionadas (stats::t.test, paired=TRUE) si la inferencia sobre "
        "el cambio medio es defendible: informa cambio medio, IC del 95 %, t, grados de libertad y p; "
        "estima d_z como media del cambio dividida por su desviación estándar e IC si es estimable. "
        "Si se justifica Wilcoxon de rangos con signo, explicita el supuesto de simetría de las diferencias "
        "y el cambio de estimando, informa V, p, estimador de Hodges–Lehmann e IC, y correlación biserial "
        "de rangos pareados; documenta ceros, empates y método exacto o aproximado. Ante asimetría fuerte "
        "considera el contraste de signos para otro estimando, sin presentarlo como prueba de medias. "
        "Interpreta dirección, magnitud y precisión del cambio; el diseño antes-después sin control "
        "no permite atribuirlo causalmente a una intervención."
    ),
    "Correlación": (
        "Estima la asociación entre todos los pares de [variables] usando pares completos, es decir "
        "cada par con los casos válidos en sus dos variables, y declara el n de cada par porque no "
        "tiene que coincidir. Comprueba escala, variabilidad y n efectivo; no codifiques categorías "
        "nominales como cantidades. Elige el método par a par según la naturaleza de las dos "
        "variables y las pruebas de normalidad, y no apliques un único método a toda la matriz. "
        "Primero clasifica cada variable con la clase declarada en el diccionario y contrasta su "
        "normalidad con Shapiro–Wilk, informando W y p; para cada par de cuantitativas evalúa además "
        "la normalidad bivariante con MVN::mvn sobre esas dos columnas usando mvn_test igual a hz y "
        "a mardia, sin confundirla con dos pruebas marginales. Llama a mvn con el data.frame de las "
        "dos columnas y mvn_test, y con nada más: en esta versión el argumento se llama mvn_test, no "
        "mvnTest, y no existen desc, univariateTest ni multivariatePlot, de modo que pasarlos detiene "
        "la ejecución con el error el argumento no fue usado. Una llamada devuelve una sola prueba, "
        "así que repítela con mvn_test igual a hz y a mardia; lee el componente "
        "multivariate_normality, cuyas columnas son Test, Statistic, p.value, Method y MVN, "
        "respetando esas mayúsculas, y limpia el p.value, que es texto y puede llegar como <0.001, "
        "con sub('>', '', sub('<', '', trimws(as.character(p.value)))) antes de compararlo con alfa. "
        "Luego aplica esta regla y declárala "
        "en la tabla: dos cuantitativas con normalidad bivariante no rechazada y relación lineal, "
        "Pearson con stats::cor.test; dos cuantitativas con normalidad rechazada, asimetría marcada "
        "o atípicos influyentes, Spearman, y si además hay empates abundantes o n pequeño, tau-b de "
        "Kendall; cualquier par con una ordinal, Spearman, o Kendall con pocos niveles y muchos "
        "empates; una binaria con una cuantitativa, Pearson identificado como correlación "
        "punto-biserial, declarando qué categoría vale 1; dos binarias, Pearson identificado como "
        "coeficiente phi; y si una variable es nominal de más de dos categorías, no calcules "
        "ninguna correlación con ella, dilo y remite a una tabla de contingencia con V de Cramer. "
        "Presenta la matriz de coeficientes con el método de cada celda y, además, una tabla por "
        "par con las dos variables, el método elegido, el motivo en una frase que cite el resultado "
        "de normalidad, coeficiente, "
        "n, IC del 95 %, estadístico de contraste, grados de libertad si existen y p bilateral; "
        "para Pearson usa el IC de Fisher cuando sea aplicable. Si Spearman o Kendall no ofrecen IC "
        "analítico, calcula bootstrap de pares con semilla fija y 2000 réplicas, identificando el método "
        "y las réplicas degeneradas, o declara por qué no es estimable. Examina la sensibilidad a "
        "valores influyentes sin excluirlos automáticamente. No interpretes coeficiente cercano a cero "
        "como ausencia de toda relación; distingue linealidad y monotonía. Con k variables hay "
        "k(k-1)/2 pares: informa cuántos contrastes se han realizado y añade el p ajustado por Holm "
        "con stats::p.adjust junto al p sin ajustar, sin sustituir uno por otro, y no selecciones "
        "para el relato solo los pares significativos. Interpreta signo, intensidad, "
        "precisión y límites del diseño, sin causalidad ni equivalencia por p no significativo."
    ),
    "Regresión": (
        "Ajusta una regresión lineal de [respuesta] sobre [predictores] mediante mínimos cuadrados "
        "ordinarios (stats::lm), con intercepto y efectos principales. Comprueba que la respuesta sea "
        "cuantitativa continua; si es binaria, ordinal o de recuento, solicita aclarar el modelo antes "
        "de aplicar regresión lineal. Declara fórmula, codificación de factores, categorías de referencia, "
        "n inicial, casos completos y n/p; detecta predictores constantes, matriz singular y coeficientes "
        "no identificables antes de los diagnósticos. Presenta B no estandarizado, error estándar, "
        "t, grados de libertad, p e IC del 95 %, R², R² ajustado, error estándar residual y contraste "
        "F global con grados de libertad y p. Evalúa heterocedasticidad con Breusch–Pagan "
        "(lmtest::bptest), indicando si se utiliza la versión studentizada de Koenker; informa estadístico, "
        "grados de libertad, p e hipótesis nula. Si hay heterocedasticidad, añade inferencia robusta HC3 "
        "(sandwich::vcovHC y lmtest::coeftest), incluyendo IC robustos y distinguiéndola de la convencional, "
        "sin afirmar que HC3 corrige especificación incorrecta. Evalúa multicolinealidad con car::vif: "
        "VIF por término de un grado de libertad, GVIF, grados de libertad y GVIF^(1/(2*Df)) para factores "
        "multidimensionales, sin comparar indiscriminadamente GVIF bruto con umbrales de VIF. Calcula "
        "índices de condición a partir de valores singulares de la matriz de diseño con columnas "
        "escaladas a norma unitaria, explicando si se incluye el intercepto; señala dependencias exactas "
        "y no interpretes un índice aislado como prueba concluyente. Con un único predictor explica "
        "cuándo VIF no es aplicable. Contrasta normalidad de los residuos con Shapiro–Wilk cuando sea "
        "aplicable, informando W y p y su limitación con n grande. Examina especificación funcional con "
        "Ramsey RESET (lmtest::resettest) cuando sea estimable, sin atribuir el rechazo a una causa única. "
        "Resume residuos studentizados, leverage y distancia de Cook con índices de fila; usa umbrales "
        "solo como alertas, sin eliminar casos. La independencia depende del diseño; usa Durbin–Watson "
        "solo si existe un orden temporal declarado, nunca por el orden accidental de las filas. "
        "Interpreta cada B como cambio esperado en la respuesta por unidad, manteniendo constantes los "
        "demás predictores, y los factores respecto a su referencia. Explica ajuste, incertidumbre, "
        "diagnósticos, limitaciones y posibles acciones; no equipares asociación ajustada con causalidad "
        "ni R² con validación predictiva."
    ),
    "Fiabilidad": (
        "Evalúa la consistencia interna de [ítems] con coefficientalpha como paquete principal. Comprueba número de ítems, escalas de "
        "respuesta, categorías observadas, variabilidad y datos faltantes. No inviertas ítems automáticamente "
        "por correlación negativa ni deduzcas su clave del nombre: solicita la dirección de los ítems "
        "y el rango teórico si no constan. Informa casos válidos bajo el tratamiento elegido de ausentes; "
        "no imputes ni uses eliminación por pares sin explicitarlo. Estima alfa de Cronbach bruto y "
        "estandarizado con coefficientalpha::alpha, IC del 95 % identificando el método, correlaciones ítem-total "
        "corregidas y alfa al eliminar cada ítem. Evalúa dimensionalidad mediante análisis paralelo "
        "(psych::fa.parallel, análisis factorial común, semilla fija) antes de justificar omega total "
        "con coefficientalpha::omega; declara modelo factorial, método y limitaciones. Omega jerárquico solo si "
        "un modelo con factor general es defendible e identificable; no lo fuerces en escalas pequeñas. "
        "Para ítems ordinales con pocas categorías considera matriz policórica y coeficientes ordinales, "
        "identificándolos y comprobando que la matriz sea estimable, sin mezclarlos con los de Pearson. "
        "Interpreta precisión, redundancia y dimensionalidad; no elimines ítems solo para maximizar alfa "
        "ni concluyas validez o unidimensionalidad por un coeficiente alto. Si el número de ítems o n "
        "impide un análisis, explica qué no es estimable en lugar de forzarlo."
    ),
}
TEMPLATES.update({
    "Análisis factorial confirmatorio": (
        "Contrasta este modelo de medida mediante análisis factorial confirmatorio con lavaan::cfa. "
        "Modelo especificado por el investigador: [factores]. Escribe la sintaxis de lavaan con una "
        "línea =~ por variable latente y exactamente esos indicadores; no añadas, quites ni reasignes "
        "indicadores, y no introduzcas cargas cruzadas, residuos correlacionados ni factores de "
        "segundo orden que no se hayan pedido. Si alguna latente tiene solo dos indicadores, indica "
        "que queda identificada únicamente gracias a su correlación con las demás y que tres "
        "indicadores son preferibles. Con más de una variable latente deja libres todas las "
        "covarianzas entre latentes, que es el comportamiento por omisión de lavaan; no fijes ninguna "
        "a cero ni impongas ortogonalidad, y declara explícitamente que el modelo es oblicuo. "
        "Informa n válido, ausentes por indicador, parámetros libres, grados de libertad e "
        "identificación. Fija la escala latente con std.lv=TRUE o con el primer indicador como "
        "marcador, declara la elección y recuerda que la solución estandarizada no depende de ella. "
        "Antes de estimar evalúa la normalidad multivariante de los indicadores con el paquete MVN. "
        "Comprueba requireNamespace('MVN', quietly=TRUE) y, si falta, indícalo y solicita su "
        "instalación manual, sin sustituirlo por otra prueba ni instalarlo desde el análisis. "
        "Calcula la prueba de Mardia con MVN::mvn(dat, mvn_test='mardia'), que contrasta por "
        "separado la asimetría y la curtosis multivariantes, y la de Henze-Zirkler con "
        "MVN::mvn(dat, mvn_test='hz'); en esta versión el argumento se llama mvn_test y no "
        "mvnTest, así que no uses el nombre antiguo. Presenta en una tabla el estadístico, el p y "
        "la conclusión de cada prueba tomándolos del componente multivariate_normality. Atención a "
        "su formato: en ese data.frame la columna p.value es de tipo texto y puede llegar como "
        "<0.001, de modo que as.numeric() sobre ella devuelve NA con el aviso de coerción y "
        "cualquier if que dependa de ese valor se detiene con el error de valor ausente donde "
        "TRUE/FALSE es necesario. Antes de comparar, limpia los símbolos con "
        "sub('>', '', sub('<', '', trimws(as.character(p.value)))), sin usar clases de caracteres "
        "entre corchetes, y convierte después, tratando <0.001 como menor "
        "que 0,001; como alternativa usa la columna MVN, que ya indica la conclusión, detectándola "
        "con grepl('Not normal', ...). La conclusión que escribas debe ser coherente con el p: por "
        "debajo de alfa se rechaza la normalidad, y un p menor que 0,001 no puede presentarse como "
        "que no se rechaza. Decide el estimador con una condición envuelta en isTRUE() "
        "y, si la prueba no es evaluable, dilo y continúa con MLR en lugar de interrumpir. Añade la "
        "normalidad univariante de univariate_normality y la asimetría y curtosis de descriptives, "
        "comprobando antes con names() o str() si la curtosis devuelta es bruta o en exceso para no "
        "interpretar un valor próximo a tres como exceso elevado. Interpreta ambas pruebas: Mardia "
        "distingue qué componente se desvía y es sensible al tamaño muestral, y Henze-Zirkler "
        "detecta desviaciones generales de la normal multivariante; con n grande ambas rechazan "
        "desviaciones triviales, de modo que acompaña el p con la magnitud de la asimetría y la "
        "curtosis y no interpretes p>0,05 como demostración de normalidad. Elige el estimador con "
        "esta regla declarada y explícita. Si algún indicador es ordinal con pocas categorías usa "
        "estimator='WLSMV' y declara en ordered= exactamente qué variables son ordinales, "
        "explicando que entonces se modelan umbrales y correlaciones policóricas y que las pruebas "
        "de normalidad multivariante no son el criterio aplicable a ese caso. Si los indicadores son "
        "continuos y ni Mardia ni Henze-Zirkler rechazan la normalidad multivariante, ML es "
        "admisible, e indica que MLR sigue siendo una elección segura. Si se rechaza la normalidad "
        "multivariante, el estimador por defecto es estimator='MLR' con errores estándar robustos "
        "e índices escalados. Declara siempre el estimador utilizado, la prueba que lo justifica y "
        "que cambiarlo altera errores estándar, contrastes e índices de ajuste. "
        "Usa missing='fiml' con ML, informando del supuesto MAR. "
        "Comprueba lavInspect(ajuste, 'converged'), varianzas residuales negativas, cargas "
        "estandarizadas mayores que uno, correlaciones latentes fuera de los límites y matrices no "
        "definidas positivas; si la solución es inadmisible, no presentes sus índices como válidos. "
        "Presenta con fitMeasures el contraste exacto y los índices aproximados, usando los nombres "
        "escalados o robustos cuando el estimador lo sea: chisq.scaled, df, pvalue.scaled, "
        "cfi.robust, tli.robust, rmsea.robust con rmsea.ci.lower.robust y rmsea.ci.upper.robust, y "
        "srmr. Trata los valores de referencia habituales como orientación, no como aprobado. "
        "Añade el ajuste local con lavResiduals(ajuste), cuyo tipo por omisión es 'cor_bentler': no "
        "pases type='correlation', que no existe y detiene el análisis; examina la matriz cov.z y "
        "localiza los residuos de correlación grandes. Consulta lavaan::modindices con la advertencia "
        "de que respecificar según esos índices capitaliza el azar. Si una llamada falla por un "
        "argumento, consulta la ayuda de la versión instalada con AYUDA: lavaan::lavResiduals o "
        "AYUDA: semTools::htmt antes de reintentar, y nunca inventes argumentos. "
        "Presenta las cargas con standardizedSolution(ajuste) filtrando op=='=~', con est.std, se, "
        "ci.lower y ci.upper, las varianzas residuales y la fiabilidad del indicador como carga al "
        "cuadrado. Calcula la fiabilidad compuesta con semTools::compRelSEM(ajuste, simplify=TRUE), "
        "que devuelve un vector numérico por factor (sin simplify devuelve una lista con texto "
        "explicativo y no una tabla), y la varianza media extraída como media de las cargas "
        "estandarizadas al cuadrado de cada factor. Evalúa de forma explícita si cada escala es "
        "fiable y válida según criterios aceptados: cargas estandarizadas desde 0,70, tolerando "
        "desde 0,50 con justificación; varianza media extraída desde 0,50 como validez convergente; "
        "fiabilidad compuesta u omega desde 0,70, y señala valores por encima de 0,95 como posible "
        "redundancia de ítems. Con más de una variable latente añade un bloque completo de validez "
        "discriminante. Primero el criterio de Fornell-Larcker: compara la raíz de la varianza media "
        "extraída de cada factor con el valor absoluto de sus correlaciones latentes obtenidas con "
        "lavInspect(ajuste, 'cor.lv'), y presenta la matriz con las raíces en la diagonal. Después "
        "la razón heterorrasgo-monorrasgo: calcula la matriz clásica con "
        "semTools::htmt(modelo, data=dat, htmt2=FALSE) y la versión basada en la media geométrica "
        "con semTools::htmt(modelo, data=dat, htmt2=TRUE), ambas con absolute=TRUE, pasando la "
        "misma sintaxis y los mismos datos del ajuste y añadiendo ordered= si los indicadores son "
        "ordinales; recuerda que htmt recibe el modelo y los datos, no el objeto ajustado. Obtén "
        "intervalos de confianza por bootstrap percentil con boot::boot y boot.ci sobre remuestreos "
        "de filas que recalculen htmt en cada réplica, con semilla declarada, al menos 2000 réplicas "
        "y conf=0.90, informando las réplicas fallidas. Presenta una tabla por pares de factores con "
        "HTMT, HTMT2 y sus intervalos, y juzga la validez discriminante por el límite superior del "
        "intervalo frente al criterio estricto de 0,85 y al más permisivo de 0,90, explicando que un "
        "límite superior por debajo del criterio es la evidencia exigida y que la estimación puntual "
        "sola no basta. Completa con el contraste del modelo anidado que fija a uno la correlación "
        "entre dos latentes, comparado con lavTestLRT; si con estimador escalado el factor de escala "
        "resulta negativo y la diferencia no es calculable, dilo e informa AIC y BIC de ambos modelos "
        "en lugar de inventar un p. Cierra con un veredicto por escala y por par de factores: qué "
        "criterios se cumplen, cuáles no, y qué implica para el uso del instrumento. Declara las "
        "limitaciones: tamaño muestral y casos por parámetro, amplitud de los intervalos del HTMT y "
        "del HTMT2, resultado de las pruebas de normalidad multivariante y estimador que han "
        "justificado, "
        "cargas cruzadas no modeladas y dependencia de la estructura declarada. No afirmes que la "
        "estructura queda demostrada ni atribuyas causalidad a las correlaciones entre factores."
    ),
    "Invarianza de medida": (
        "Comprueba si este modelo de medida funciona igual en los niveles de [grupo] mediante "
        "análisis factorial confirmatorio multigrupo con lavaan y semTools. Modelo especificado por "
        "el investigador: [factores]. Escribe la sintaxis con una línea =~ por variable latente y "
        "exactamente esos indicadores, deja libres todas las covarianzas entre latentes en cada "
        "grupo y no modifiques la estructura. La invarianza solo tiene sentido sobre un modelo de "
        "medida que ajuste razonablemente en cada grupo por separado. Informa n por grupo, ausentes por ítem y grupo, y advierte de grupos "
        "pequeños o muy desequilibrados, que reducen la potencia para detectar falta de invarianza. "
        "Antes de estimar evalúa la normalidad multivariante de los indicadores con el paquete MVN, "
        "y hazlo dentro de cada grupo por separado, porque el estimador debe servir para todos: "
        "comprueba requireNamespace('MVN', quietly=TRUE) y, si falta, indícalo y solicita su "
        "instalación manual sin sustituirlo. Calcula para cada grupo la prueba de Mardia con "
        "MVN::mvn(subset(dat, grupo == nivel, select = columnas), mvn_test='mardia') y la de Henze-Zirkler con "
        "MVN::mvn(subset(dat, grupo == nivel, select = columnas), mvn_test='hz'); el argumento se llama mvn_test y no mvnTest. "
        "Presenta una tabla con grupo, prueba, estadístico, p y conclusión tomados de "
        "multivariate_normality, y añade la asimetría y la curtosis por grupo de descriptives, "
        "comprobando con names() o str() si la curtosis es bruta o en exceso. Esa columna p.value es "
        "de tipo texto y puede llegar como <0.001, así que as.numeric() sobre ella devuelve NA con "
        "aviso de coerción y cualquier if que dependa de ese valor se detiene con el error de valor "
        "ausente donde TRUE/FALSE es necesario: limpia antes los símbolos con "
        "sub('>', '', sub('<', '', trimws(as.character(p.value)))) y convierte después, o usa la "
        "columna MVN detectándola con grepl('Not normal', ...), y envuelve la condición en isTRUE(). "
        "La conclusión que escribas debe ser coherente con el p: por debajo de alfa se rechaza la "
        "normalidad, y un p menor que 0,001 no puede presentarse como que no se rechaza. "
        "Elige el estimador con esta regla declarada. Si algún indicador es ordinal con pocas "
        "categorías usa WLSMV declarando en ordered= exactamente qué variables son ordinales, con la "
        "secuencia de umbrales de semTools::measEq.syntax, y explica que entonces se contrastan "
        "umbrales y cargas y no medias de ítems, y que las pruebas de normalidad multivariante no son "
        "el criterio aplicable a ese caso. Si los indicadores son continuos y ningún grupo rechaza la "
        "normalidad multivariante, ML es admisible, e indica que MLR sigue siendo una elección segura. "
        "Si algún grupo la rechaza, el estimador por defecto para toda la secuencia es MLR, con "
        "contrastes escalados y la corrección adecuada en lavaan::lavTestLRT; no mezcles estimadores "
        "entre pasos ni entre grupos. Declara el estimador utilizado, la prueba que lo justifica y "
        "que cambiarlo altera errores estándar, contrastes e índices. "
        "Ajusta y presenta primero el modelo por grupo; si en alguno la solución es inadmisible o no "
        "converge, no continúes la secuencia como si fuera comparable. Estima después la secuencia "
        "configural, métrica o débil con group.equal=c('loadings'), escalar o fuerte añadiendo "
        "'intercepts' y, cuando se solicite, estricta añadiendo 'residuals'. Para cada "
        "paso informa X² escalado, grados de libertad, p, CFI, RMSEA y SRMR, y los cambios entre "
        "modelos anidados: contraste de razón de verosimilitudes corregido con lavaan::lavTestLRT "
        "sobre los mismos casos, ΔCFI y ΔRMSEA. Presenta los criterios orientativos habituales como "
        "referencia y no como norma, y nunca interpretes p>0,05 ni un ΔCFI pequeño como demostración "
        "de invarianza: son ausencia de evidencia de falta de invarianza. Si un paso falla, localiza "
        "los parámetros responsables mediante índices de modificación y restricciones liberadas de "
        "una en una, documentando el orden seguido y el riesgo de capitalizar el azar; informa "
        "entonces de invarianza parcial indicando exactamente qué cargas o interceptos quedan libres "
        "y cuántos parámetros se han liberado. Explica las consecuencias para el uso práctico: con "
        "invarianza métrica pueden compararse covarianzas y relaciones estructurales, pero la "
        "comparación de medias latentes o de puntuaciones observadas entre grupos exige invarianza "
        "escalar al menos parcial. Si se alcanza, estima las diferencias de medias latentes con su "
        "IC del 95 % en la métrica declarada. Interpreta qué significa el resultado para la "
        "comparabilidad del instrumento y advierte de que la invarianza no se demuestra con una "
        "muestra única ni implica validez de contenido."
    ),
    "Normalidad": (
        "Comprueba la normalidad de [variables] con el paquete MVN. Pruebas multivariantes "
        "solicitadas: [pruebas_multivariantes]. Pruebas univariantes solicitadas: "
        "[pruebas_univariantes]. Calcula exactamente las pedidas, ninguna más y ninguna menos, "
        "usando como valor del argumento el código que figura entre paréntesis en cada nombre. "
        "Comprueba requireNamespace('MVN', quietly=TRUE) y, si falta el paquete, indícalo y "
        "solicita su instalación manual sin sustituirlo por otra prueba. MVN::mvn devuelve una "
        "sola prueba multivariante por llamada, así que invócalo una vez por cada prueba pedida "
        "con mvn_test igual a su código, y otra vez por cada prueba univariante con "
        "univariate_test igual al suyo; los únicos valores válidos en esta versión son "
        "mardia, hz, hw, royston, doornik_hansen y energy para las multivariantes, y SW, SF, AD, "
        "CVM y Lillie para las univariantes. El argumento se llama mvn_test, no mvnTest: no uses "
        "el nombre antiguo ni inventes códigos. Llama a mvn con los argumentos imprescindibles y "
        "nada más: el data.frame y mvn_test, o el data.frame y univariate_test. No pases transform, "
        "power_family ni multivariate_outlier_method para desactivarlos, porque sus valores por "
        "omisión ya los desactivan y son cadenas de texto: pasarles NULL o FALSE detiene la "
        "ejecución con un error de match.arg del tipo arg must be NULL or a character vector. Si "
        "alguna vez los necesitas, power_family admite none, bcPower, bcnPower o yjPower, y "
        "multivariate_outlier_method admite none, quan o adj. Tampoco pases mvn_test=NULL ni "
        "univariate_test=NULL: ambos esperan siempre uno de sus códigos. Respeta las mayúsculas de "
        "las columnas devueltas y no mezcles las de una familia con las de la otra: "
        "multivariate_normality devuelve Test, Statistic, p.value, Method y MVN, más df solo en "
        "Doornik-Hansen, mientras que univariate_normality devuelve Test, Variable, Statistic, "
        "p.value y Normality, sin Method y sin MVN. Pedir r$Method o r$MVN al componente "
        "univariante devuelve NULL y detiene la ejecución con el error los argumentos implican un "
        "número diferente de filas; la conclusión univariante se lee de Normality con "
        "grepl('Not normal', ...). Escribir componente$statistic en minúscula devuelve NULL y deja "
        "la tabla vacía sin avisar. Esta es la forma correcta, comprobada; imítala y no añadas argumentos: "
        "vars <- c(nombres de las variables pedidas); "
        "dsel <- subset(dat, select = vars); "
        "limpia_p <- function(p) suppressWarnings(as.numeric(sub('>', '', sub('<', '', trimws(as.character(p)))))); "
        "r <- MVN::mvn(dsel, mvn_test = 'mardia')$multivariate_normality; "
        "fila <- data.frame(Prueba = as.character(r$Test), Estadistico = r$Statistic, "
        "p = r$p.value, Conclusion = ifelse(limpia_p(r$p.value) < 0.05, se rechaza, no se rechaza)). "
        "Repite esa llamada una vez por prueba pedida cambiando mvn_test. Para las univariantes la "
        "forma correcta es la siguiente, con sus columnas propias y sin Method ni MVN: "
        "u <- MVN::mvn(dsel, univariate_test = 'SW')$univariate_normality; "
        "filas <- data.frame(Prueba = as.character(u$Test), Variable = as.character(u$Variable), "
        "Estadistico = u$Statistic, p = u$p.value, "
        "Conclusion = ifelse(limpia_p(u$p.value) < 0.05, se rechaza, no se rechaza)). "
        "Repítela una vez por prueba univariante pedida, combina las filas con do.call(rbind, ...) y "
        "preséntalas con tabla(). Informa n analizado, ausentes por variable y qué "
        "casos se excluyen, porque el análisis usa casos completos en todas las variables. "
        "Presenta dos tablas, una por familia, con prueba, estadístico, p, método declarado por el "
        "paquete (asintótico o bootstrap) y conclusión, tomando los valores de los componentes "
        "multivariate_normality y univariate_normality. Sobre los grados de libertad: de las "
        "pruebas multivariantes solo Doornik-Hansen devuelve la columna df, porque es la única que "
        "compara su estadístico con una X² con 2k grados de libertad para k variables. No añadas "
        "una columna de grados de libertad llena de NA: inclúyela únicamente si alguna prueba "
        "pedida la devuelve, comprobando su presencia con names() antes de usarla, y para las demás "
        "escribe en esa celda un guion seguido de la distribución de referencia, nunca NA ni una "
        "celda vacía: para la curtosis de Mardia normal estándar, para Henze-Zirkler y Henze-Wagner "
        "aproximación lognormal, para Royston grados de libertad equivalentes que el paquete no "
        "devuelve, y para la prueba de energía remuestreo. Para la asimetría de Mardia informa "
        "siempre sus grados de libertad calculándolos a partir del número de variables k como "
        "k(k+1)(k+2)/6, marcados como derivados y no devueltos por el paquete, y comprueba que "
        "coinciden con los que correspondan a las k variables analizadas. Atención al formato: la columna p.value es de tipo texto y puede "
        "llegar como <0.001, de modo que as.numeric() sobre ella devuelve NA con aviso de coerción "
        "y cualquier if que dependa de ese valor se detiene con el error de valor ausente donde "
        "TRUE/FALSE es necesario; limpia antes los símbolos con "
        "sub('>', '', sub('<', '', trimws(as.character(p.value)))) y convierte después, tratando "
        "<0.001 como menor que 0,001, o usa la columna MVN, que ya indica la conclusión, "
        "detectándola con grepl('Not normal', ...), y envuelve cualquier condición en isTRUE(). "
        "La conclusión de cada fila debe ser coherente con su p y nunca puede contradecirlo: con un "
        "p por debajo del alfa declarado se rechaza la normalidad, y un p menor que 0,001 jamás "
        "puede etiquetarse como que no se rechaza. Deriva la conclusión del p ya limpiado "
        "comparándolo con alfa, comprueba que coincide con lo que dice la columna MVN y, si no "
        "coincidieran, informa de la discrepancia en lugar de elegir una de las dos. No te apoyes "
        "en los símbolos de esa columna, que son marcas Unicode fáciles de invertir al leerlas. Si "
        "el p no se puede convertir a número, escribe que no es evaluable en vez de inventar una "
        "conclusión. Añade la asimetría y la curtosis de cada variable desde el componente "
        "descriptives, "
        "comprobando antes con names() o str() si la curtosis devuelta es bruta o en exceso para "
        "no interpretar un valor próximo a tres como exceso elevado. Interpreta cada prueba por lo "
        "que realmente contrasta, sin presentarlas como intercambiables: Mardia evalúa por "
        "separado la asimetría y la curtosis multivariantes e indica qué componente se desvía; "
        "Henze-Zirkler y Henze-Wagner son pruebas consistentes frente a desviaciones generales de "
        "la normal multivariante; Royston se construye a partir de Shapiro-Wilk y exige entre 3 y "
        "5000 casos, siendo sensible a los empates; Doornik-Hansen transforma asimetría y curtosis "
        "y devuelve un X² con sus grados de libertad; la prueba de energía obtiene su p por "
        "bootstrap, así que fija una semilla con set.seed antes de llamarla, declara el número de "
        "réplicas y advierte de que su p varía entre ejecuciones. Si las pruebas pedidas no "
        "coinciden en su conclusión, dilo explícitamente y explica a qué tipo de desviación es "
        "sensible cada una en lugar de elegir la que más convenga. Acompaña siempre los p con la "
        "magnitud de la desviación: con n grande cualquier prueba rechaza desviaciones triviales, "
        "y con n pequeño ninguna tiene potencia, de modo que no interpretes p>0,05 como "
        "demostración de normalidad ni un rechazo como prueba de que el análisis posterior sea "
        "inválido. Con varias variables, recuerda que los p univariantes se acumulan: señala "
        "cuántas pruebas se han realizado y, si procede, aplica un ajuste declarado tipo Holm como "
        "orientación con stats::p.adjust(p, method = 'holm'), siempre en minúscula sobre los p ya "
        "limpiados: p.adjust valida el nombre con match.arg y escribir Holm detiene la ejecución. "
        "Si se solicita, localiza observaciones atípicas multivariantes con "
        "multivariate_outlier_method igual a quan o adj, fijando outlier_seed para que el resultado "
        "sea reproducible, e informa de las observaciones señaladas con su distancia de Mahalanobis "
        "sin eliminar ningún caso. MVN puede aplicar transformaciones de potencia mediante transform "
        "o power_family: no las apliques en silencio; indica que están disponibles y qué cambiarían. "
        "Cierra explicando las consecuencias prácticas para el análisis que se vaya a hacer: en "
        "regresión y ANOVA el supuesto se refiere a los residuos del modelo y no a la distribución "
        "bruta de las variables; en modelos de ecuaciones estructurales la no normalidad lleva a "
        "estimadores robustos como MLR, o WLSMV con indicadores ordinales; en comparación de medias "
        "lleva a Welch, a inferencia robusta o a contrastes de rangos, declarando que estos últimos "
        "cambian el estimando. No recomiendes eliminar casos ni transformar variables como solución "
        "automática."
    ),
    "Mediación": (
        "Estima el efecto de [predictor] sobre [respuesta] a través de [mediador] mediante un modelo "
        "de senderos con lavaan::sem y variables observadas. Declara el modelo y el orden supuesto "
        "antes de estimar: predictor sobre mediador, sendero a; mediador sobre respuesta controlando "
        "el predictor, sendero b; efecto directo c primado; efecto indirecto definido explícitamente "
        "como ab mediante := en la sintaxis; y efecto total como suma declarada. Informa n válido, "
        "ausentes, descriptivos y correlaciones de las tres variables, con su escala y unidades. "
        "Exige respuesta y mediador cuantitativos para esta parametrización; si alguno es binario u "
        "ordinal, dilo y propón la especificación adecuada en lugar de aplicar la fórmula del "
        "producto a una escala que no la admite. Usa estimación ML con missing='fiml' declarando el "
        "supuesto MAR, y comprueba convergencia, varianzas residuales admisibles y colinealidad "
        "entre predictor y mediador, que infla los errores estándar de b y c primado. Calcula el IC "
        "del efecto indirecto por bootstrap con se='bootstrap' y al menos 5000 réplicas, semilla "
        "declarada e intervalos percentiles y corregidos por sesgo identificados como tales; no "
        "uses la prueba de Sobel como contraste principal porque supone normalidad del producto, "
        "y documenta las réplicas fallidas si las hay. Esta es la forma correcta, comprobada en R "
        "con este mismo intérprete; imítala cambiando solo los nombres de las variables y no añadas "
        "argumentos ni funciones que no aparezcan aquí: "
        "vars <- c('[predictor]', '[mediador]', '[respuesta]'); "
        "sub <- stats::na.omit(subset(dat, select = vars)); "
        "modelo <- '[mediador] ~ a*[predictor] \\n [respuesta] ~ cp*[predictor] + b*[mediador] \\n "
        "ab := a*b \\n total := cp + a*b'; "
        "set.seed(2026); "
        "fit <- lavaan::sem(modelo, data = sub, estimator = 'ML', missing = 'fiml', "
        "se = 'bootstrap', bootstrap = 5000); "
        "pe <- lavaan::parameterEstimates(fit, boot.ci.type = 'perc', level = 0.95); "
        "bc <- lavaan::parameterEstimates(fit, boot.ci.type = 'bca.simple', level = 0.95); "
        "st <- lavaan::standardizedSolution(fit); "
        "f <- subset(pe, label %in% c('a', 'b', 'cp', 'ab', 'total')). "
        "Las filas se eligen con subset y label, nunca por posición, y las columnas disponibles son "
        "lhs, op, rhs, label, est, se, z, pvalue, ci.lower y ci.upper, salvo en "
        "standardizedSolution, donde la estimación se llama est.std. El n analizado es "
        "lavaan::lavInspect(fit, 'ntotal') y las réplicas conservadas son nrow de "
        "lavaan::lavInspect(fit, 'boot'), cuyos atributos error.idx y nonadmissible dan las "
        "fallidas. No existen standardizedEstimates, el argumento boot.ci, ni las medidas "
        "chisq.df, srmr.pvalue, bicadj o df.minus; se='bca' no es un valor válido, el método del "
        "intervalo se elige con boot.ci.type igual a perc o a bca.simple sobre un ajuste hecho con "
        "se='bootstrap'; y los modelos no se comparan con anova sino con lavaan::lavTestLRT. "
        "Este modelo de tres variables observadas suele quedar saturado, con cero grados de "
        "libertad: compruébalo con lavaan::fitMeasures(fit, 'df') y, si es cero, dilo y no "
        "presentes CFI, RMSEA ni chi-cuadrado como prueba de que el modelo ajusta. "
        "Presenta en una tabla a, b, c primado, el "
        "efecto total y el indirecto, con estimación, error estándar, IC del 95 %, p cuando proceda "
        "y versiones estandarizadas; advierte de que la proporción mediada es inestable cuando el "
        "efecto total es pequeño o los senderos tienen signos opuestos, y no la presentes como "
        "porcentaje fiable en ese caso. No sigas los pasos clásicos de Baron y Kenny como requisito: "
        "un efecto total no significativo no impide un indirecto relevante, y un indirecto "
        "significativo no exige significación del total. Explicita los supuestos causales que "
        "sostienen la interpretación mediadora: orden temporal real entre las tres medidas, ausencia "
        "de confusión no medida de las relaciones predictor–mediador y mediador–respuesta, ausencia "
        "de causalidad inversa y de interacción no modelada entre predictor y mediador. Si los datos "
        "son transversales, declara que el modelo es una descomposición estadística compatible con "
        "varias historias causales y no una prueba de mecanismo. Interpreta dirección, magnitud y "
        "precisión en unidades originales, y no afirmes mediación demostrada."
    ),
    "Moderación": (
        "Comprueba si el efecto de [predictor] sobre [respuesta] cambia según [moderador] mediante un "
        "modelo lineal con interacción usando stats::lm. Informa n válido, ausentes, descriptivos y "
        "rango de las tres variables, y declara la naturaleza del moderador: cuantitativo o factor "
        "con sus niveles observados y su referencia. Especifica la fórmula con el término producto y "
        "sus efectos principales, nunca la interacción sola. Centra las variables cuantitativas en "
        "valores explícitos, preferentemente la media, declara el centrado y recuerda que cambia la "
        "interpretación de los efectos principales, que pasan a ser efectos condicionales en el "
        "valor cero del centrado, pero no altera el coeficiente de la interacción. Presenta el "
        "modelo aditivo y el modelo con interacción ajustados a los mismos casos completos y "
        "compáralos con F parcial, informando modelos, F, grados de libertad, p y el incremento de "
        "R²; añade f² de Cohen para ese incremento como tamaño de efecto de la moderación. No "
        "interpretes la colinealidad entre el producto y sus componentes como un problema por sí "
        "misma si las variables están centradas, pero informa de VIF o GVIF y de los índices de "
        "condición. Si la interacción es relevante, describe la moderación con pendientes simples: "
        "calcula con emmeans::emtrends la pendiente del predictor en valores justificados del "
        "moderador, por ejemplo la media y la media ± una desviación típica si están dentro del "
        "rango observado, y presenta estimación, error estándar, IC del 95 % y p en cada valor, "
        "evitando extrapolar. Con moderador categórico usa emmeans para las pendientes por nivel y "
        "sus contrastes, con ajuste declarado para la familia de comparaciones. Explora la región de "
        "significación recorriendo valores del moderador con emtrends y declara en qué intervalo el "
        "efecto difiere de cero, indicando que ese límite es una lectura descriptiva del IC y no una "
        "prueba adicional. Evalúa linealidad, normalidad de residuos con Shapiro–Wilk cuando sea "
        "aplicable, heterocedasticidad con lmtest::bptest e influencia con residuos studentizados, "
        "leverage y Cook, prestando atención a los casos extremos del producto, que dominan la "
        "estimación. Ante heterocedasticidad informa además inferencia HC3 con sandwich y lmtest, "
        "separada de la clásica. Interpreta la forma de la moderación en unidades originales y "
        "advierte de que una interacción estadística no prueba un mecanismo ni causalidad, y que su "
        "detección exige más potencia que un efecto principal."
    ),
    "ANOVA de medidas repetidas": (
        "Compara las medidas repetidas [medidas] dentro de los mismos casos, considerando además el "
        "factor entre sujetos [grupo], mediante ANOVA de diseño mixto con afex. Declara el diseño "
        "antes de estimar: las columnas seleccionadas son niveles de un factor intrasujeto medido en "
        "las mismas personas, cada fila es un caso y el factor entre sujetos clasifica a esos casos. "
        "Construye explícitamente el formato largo con un identificador de caso creado a partir del "
        "número de fila, declara ese paso y comprueba que cada caso aporte una observación por nivel. "
        "Informa n por grupo y por nivel, ausentes y qué casos se excluyen; el análisis usa casos "
        "completos en todos los niveles, así que documenta la pérdida y advierte del sesgo si es "
        "apreciable. Exige medidas cuantitativas comparables en escala y unidades; si los niveles no "
        "son el mismo constructo medido en momentos u condiciones distintas, dilo y no fuerces el "
        "análisis. Ajusta el modelo con afex::aov_ez indicando identificador, variable dependiente, "
        "factor intrasujeto y factor entre sujetos, con type=3 y fun_aggregate declarado solo si hay "
        "repeticiones. Presenta la tabla con F, grados de libertad, p y tamaños de efecto generalizado "
        "y parcial, identificando cuál es cada uno. Para los efectos intrasujeto con más de dos "
        "niveles contrasta la esfericidad con la prueba de Mauchly e informa epsilon de "
        "Greenhouse–Geisser y Huynh–Feldt, presentando los grados de libertad corregidos como "
        "resultado principal cuando el supuesto falle; no interpretes p>0,05 en Mauchly como prueba "
        "de esfericidad. Evalúa normalidad de los residuos del modelo con Shapiro–Wilk cuando sea "
        "aplicable y valores atípicos por caso, e indica el efecto potencial de unos pocos casos "
        "sobre un diseño intrasujeto. Descompón los efectos con emmeans: medias marginales por "
        "nivel y grupo con IC del 95 %, comparaciones por pares con ajuste de Tukey o Holm "
        "declarado, y contrastes de interacción cuando el diseño lo pida; especifica la rejilla de "
        "referencia y las ponderaciones. Si la interacción es relevante, interpreta los efectos "
        "simples y no solo los principales. Cuando el diseño esté muy desequilibrado o falten datos "
        "de forma sustancial, señala que un modelo mixto con lme4 sería preferible y por qué, sin "
        "cambiar silenciosamente el método. Interpreta cambios entre niveles y diferencias entre "
        "grupos en unidades originales, con su precisión, y sin atribuir causalidad al paso del "
        "tiempo ni a la pertenencia al grupo."
    ),
    "Modelo multinivel": (
        "Modela [respuesta] a partir de [predictores] teniendo en cuenta que las observaciones se "
        "agrupan en [agrupamiento], mediante un modelo lineal mixto con lme4::lmer. Declara la "
        "estructura de datos antes de estimar: qué representa cada fila, qué representa cada "
        "agrupación y a qué nivel está medido cada predictor. Informa n total, número de grupos, "
        "tamaño de grupo mínimo, mediano y máximo, grupos con una sola observación y ausentes; "
        "advierte de que con pocos grupos, por debajo de unos treinta, las varianzas aleatorias y "
        "sus intervalos son poco fiables. Ajusta primero el modelo nulo con intercepto aleatorio y "
        "presenta la correlación intraclase calculada a partir de las varianzas estimadas, "
        "explicando que cuantifica la proporción de varianza entre grupos y justifica el enfoque "
        "multinivel. Añade después los efectos fijos con REML para estimar varianzas y declara la "
        "fórmula completa, incluida la parte aleatoria. Para los predictores de nivel individual "
        "distingue el componente intragrupo del intergrupo si la pregunta lo requiere, centrando "
        "dentro del grupo e incluyendo la media del grupo como predictor de nivel superior; declara "
        "la transformación y no mezcles ambas interpretaciones en un solo coeficiente. Valora "
        "pendientes aleatorias solo con justificación sustantiva y datos suficientes, comparando "
        "modelos anidados reajustados con REML=FALSE mediante razón de verosimilitudes y AIC, e "
        "informando que ese contraste es conservador para componentes de varianza. Comprueba "
        "convergencia, ajustes singulares, correlaciones aleatorias en los límites y matrices no "
        "definidas positivas; si el modelo es singular, simplifica la parte aleatoria y dilo, sin "
        "presentar sus errores estándar como fiables. Presenta efectos fijos con estimación, error "
        "estándar, estadístico t e IC del 95 % obtenidos con confint por perfil o bootstrap "
        "paramétrico con semilla declarada; advierte de que lmer no proporciona p por defecto porque "
        "los grados de libertad no son exactos, y si no está instalado un paquete que los aproxime, "
        "informa de los contrastes por verosimilitud en lugar de inventar un p. Informa las "
        "varianzas aleatorias y la residual con su desviación típica, y las medias marginales o "
        "pendientes de interés con emmeans indicando sobre qué nivel se promedia. Evalúa residuos "
        "condicionales, linealidad, heterocedasticidad por grupo y casos influyentes. Para respuesta "
        "binaria o de recuentos indica que corresponde glmer o glmmTMB con la familia adecuada y no "
        "este modelo gaussiano. Interpreta efectos fijos y variabilidad entre grupos en unidades "
        "originales, sin atribuir causalidad ni interpretar la agrupación como explicación."
    ),
    "Curva ROC y capacidad diagnóstica": (
        "Evalúa la capacidad de [predictores] para discriminar los valores de [respuesta] mediante "
        "curvas ROC con pROC. Exige una respuesta binaria y declara explícitamente qué nivel es el "
        "caso positivo y qué nivel el control, mediante levels= y direction= en pROC::roc; no dejes "
        "que la dirección se elija automáticamente para maximizar el área, porque eso sobreestima "
        "el rendimiento. Informa n válido, número de casos y controles, prevalencia en la muestra, "
        "ausentes y rango de cada marcador. Para cada marcador presenta el área bajo la curva con su "
        "IC del 95 % por el método de DeLong, identificado como tal, e interpreta el área como "
        "probabilidad de ordenar correctamente un caso y un control elegidos al azar, no como "
        "porcentaje de acierto. Describe la curva con sensibilidad y especificidad en puntos de "
        "corte relevantes, con sus IC calculados por bootstrap con semilla y número de réplicas "
        "declarados. Si se solicita un punto de corte, presenta al menos el de Youden y el más "
        "cercano a la esquina superior izquierda con pROC::coords, declarando el criterio, y advierte "
        "de que un corte elegido y evaluado en los mismos datos es optimista: si el tamaño lo "
        "permite, estima su rendimiento corregido por validación cruzada o bootstrap y sepáralo del "
        "aparente. Presenta valores predictivos positivo y negativo solo si la prevalencia de la "
        "muestra es representativa de la población de interés; si el diseño es de casos y controles, "
        "dilo y calcula los valores predictivos únicamente para prevalencias declaradas por el "
        "usuario, sin inventarlas. Cuando haya varios marcadores medidos en los mismos casos, "
        "compara sus áreas con pROC::roc.test mediante la prueba de DeLong para curvas emparejadas, "
        "informando estadístico, p y la diferencia de áreas con su IC, y ajusta por comparaciones "
        "múltiples si son varias. Evalúa la calibración además de la discriminación cuando el "
        "marcador sea una probabilidad predicha, y señala que un área alta no garantiza "
        "probabilidades bien calibradas ni utilidad clínica. Documenta el efecto del desequilibrio "
        "de clases y de los valores extremos, y los marcadores constantes o con escasa variabilidad, "
        "que no permiten estimar la curva. Interpreta la capacidad discriminativa, su precisión y "
        "sus límites, sin atribuir causalidad ni proponer un umbral de decisión clínica que no haya "
        "fijado el usuario."
    ),
    "Análisis de supervivencia": (
        "Analiza el tiempo hasta el evento usando [tiempo] como tiempo de seguimiento, [evento] como "
        "indicador de ocurrencia y [predictores] como covariables, mediante el paquete survival. "
        "Comprueba y declara la estructura: tiempo cuantitativo, estrictamente positivo y con "
        "unidades explícitas, e indicador codificado como 1 si el evento ocurre y 0 si el caso está "
        "censurado; si la codificación es otra, pide confirmación en lugar de adivinarla, porque "
        "invertirla cambia por completo el resultado. Informa n, número de eventos, número de "
        "censurados, porcentaje de censura, mediana de seguimiento y ausentes; advierte de que el "
        "número de eventos, y no el de casos, determina la potencia, y aplica la regla orientativa "
        "de al menos diez eventos por parámetro, declarando su incumplimiento. Construye el objeto "
        "con survival::Surv y estima primero la curva de Kaplan–Meier global y por niveles de los "
        "predictores categóricos con survival::survfit, presentando en tabla la supervivencia "
        "estimada en tiempos relevantes con su IC del 95 %, la mediana de supervivencia con IC y los "
        "casos en riesgo en cada tiempo; si la mediana no se alcanza, indícalo en lugar de "
        "extrapolar. Compara grupos con la prueba de log-rango mediante survival::survdiff, "
        "informando X², grados de libertad y p, y recuerda que esa prueba tiene más potencia cuando "
        "los riesgos son proporcionales. Ajusta después el modelo de riesgos proporcionales de Cox "
        "con survival::coxph, declarando fórmula, referencias de factores, método de empates y "
        "convergencia. Presenta coeficientes, errores estándar, razones de riesgo con IC del 95 % y "
        "p, interpretando la razón de riesgo como efecto multiplicativo sobre el riesgo instantáneo "
        "y no como razón de probabilidades ni como diferencia de tiempos. Contrasta el supuesto de "
        "proporcionalidad con survival::cox.zph global y por término, mediante residuos de "
        "Schoenfeld, informando estadístico y p; ante incumplimiento, propón estratificar con "
        "strata, modelar la interacción con el tiempo o informar efectos por periodos, declarando el "
        "cambio de estimando. Evalúa la forma funcional de las covariables continuas con residuos de "
        "martingala, la influencia con dfbeta y la capacidad discriminativa con el índice de "
        "concordancia. Explicita los supuestos: censura no informativa, inicio del seguimiento común "
        "y bien definido, y ausencia de riesgos competidores; si los hay, señala que el estimador de "
        "Kaplan–Meier sobreestima la incidencia y que procede un análisis específico. Interpreta en "
        "unidades de tiempo originales, sin causalidad."
    ),
    "Ausentes e imputación múltiple": (
        "Analiza el patrón de datos ausentes de [variables] y, si procede, aplica imputación múltiple "
        "con mice. Empieza con una descripción honesta: número y porcentaje de ausentes por variable, "
        "número de casos completos, casos con ausencia en una sola variable y en varias, y el patrón "
        "conjunto con mice::md.pattern presentado en tabla. Informa qué análisis perdería cada "
        "enfoque: cuántos casos sobreviven al análisis de casos completos y qué proporción de la "
        "muestra representa. Explora si la ausencia se asocia a variables observadas comparando "
        "descriptivos de las variables completas según la presencia o ausencia de cada variable "
        "incompleta; presenta esas comparaciones como exploración descriptiva y no como contrastes "
        "confirmatorios. Contrasta la aleatoriedad completa con la prueba de Little mediante "
        "misty::na.test, comprobando requireNamespace y declarando si el paquete falta; informa "
        "X², grados de libertad y p, y advierte de que rechazar indica que los datos no son "
        "completamente aleatorios, mientras que no rechazar no demuestra que lo sean, y de que el "
        "mecanismo no aleatorio no es contrastable con los datos observados. Explica con claridad la "
        "diferencia entre los tres mecanismos y qué supone cada método: el análisis de casos "
        "completos exige aleatoriedad completa para no sesgar, y la imputación múltiple asume "
        "aleatoriedad condicionada a las variables incluidas en el modelo de imputación. Si imputas, "
        "declara la configuración: m de al menos 20 conjuntos, maxit suficiente, semilla fija, y el "
        "método por variable según su tipo, pmm para cuantitativas, logreg para binarias, polyreg "
        "para nominales y polr para ordinales, nunca el método por defecto sin revisarlo. Declara la "
        "matriz de predictores y qué variables se incluyen como auxiliares; incluye la variable "
        "respuesta del análisis posterior en el modelo de imputación, pero advierte de que los "
        "valores imputados de la respuesta no se interpretan por sí mismos. Comprueba la calidad de "
        "la imputación: convergencia entre cadenas, número de valores imputados por variable, y "
        "comparación de la distribución de los valores observados e imputados en tablas de "
        "descriptivos; señala imputaciones fuera del rango plausible o categorías vacías. Si se pide "
        "un análisis sobre los datos imputados, ajústalo con mice::with y combina los resultados con "
        "mice::pool según las reglas de Rubin, presentando estimación agrupada, error estándar, IC "
        "del 95 %, grados de libertad, fracción de información ausente e incremento relativo de "
        "varianza, y compáralos con los de casos completos como análisis de sensibilidad. No "
        "presentes un único conjunto imputado ni la media de los imputados como si fueran datos "
        "reales, y no afirmes haber corregido el sesgo: la imputación lo reduce bajo supuestos que "
        "debes declarar."
    ),
    "Acuerdo entre evaluaciones": (
        "Cuantifica el grado de acuerdo entre las columnas [evaluaciones], que corresponden a "
        "mediciones del mismo objeto por evaluadores, instrumentos u ocasiones distintas. Declara "
        "primero el diseño, porque determina el coeficiente: si todos los objetos son valorados por "
        "los mismos evaluadores o por evaluadores distintos elegidos al azar, si el interés está en "
        "una evaluación individual o en la media de las evaluaciones, y si importa el acuerdo "
        "absoluto o solo la consistencia del orden. Si esa información no consta, pide confirmación "
        "y no elijas un coeficiente por omisión. Informa n de objetos, número de evaluaciones, "
        "ausentes por columna y por objeto, y los descriptivos de cada evaluación, incluidos media, "
        "desviación típica y rango, que revelan sesgos sistemáticos entre evaluadores. Para "
        "mediciones cuantitativas calcula el coeficiente de correlación intraclase con psych::ICC "
        "sobre un data.frame de objetos por filas y evaluaciones por columnas; presenta las formas "
        "unidireccional, de efectos aleatorios con acuerdo absoluto y de efectos mixtos con "
        "consistencia, en versión individual y promediada, con su F, grados de libertad, p e IC del "
        "95 %. Identifica de manera inequívoca qué coeficiente corresponde al diseño declarado y no "
        "presentes el mayor de todos como resultado principal. Añade el error típico de medida y la "
        "mínima diferencia detectable derivados de las varianzas, declarando su cálculo y sus "
        "unidades, porque informan del uso práctico mejor que el coeficiente. Con exactamente dos "
        "evaluaciones cuantitativas presenta además el análisis de diferencias: media de las "
        "diferencias con IC como medida de sesgo, límites de acuerdo y su dependencia de la "
        "magnitud, comprobando si la diferencia se asocia al promedio. Para evaluaciones "
        "categóricas usa el kappa de Cohen con psych::cohen.kappa, con pesos cuadráticos cuando las "
        "categorías sean ordinales, e informa el acuerdo observado, el esperado por azar, kappa con "
        "IC del 95 % y la tabla cruzada completa; advierte de que kappa depende de la prevalencia y "
        "de las distribuciones marginales, de modo que un acuerdo alto puede dar un kappa bajo con "
        "categorías muy desequilibradas, y señala las categorías con escaso uso. Con más de dos "
        "evaluadores categóricos indica el coeficiente adecuado y declara si no es estimable con los "
        "paquetes instalados. Documenta el tratamiento de ausentes y si se usan objetos completos. "
        "Interpreta el acuerdo en términos de la decisión a la que sirve la medida, usando los "
        "umbrales habituales solo como orientación declarada, y no confundas acuerdo con validez: "
        "dos evaluadores pueden coincidir sistemáticamente en un error."
    ),
})

RELIABILITY_METHOD = (
    " Para alfa y omega de las puntuaciones observadas usa explícitamente coefficientalpha::alpha "
    "y coefficientalpha::omega sobre un data.frame numérico con nombres de ítems, filas de personas "
    "y columnas de ítems; nunca pases una matriz de correlaciones como si fueran observaciones. "
    "Comprueba requireNamespace('coefficientalpha', quietly=TRUE); si falta, indícalo y solicita su "
    "instalación manual, sin sustituir el paquete ni instalarlo desde el análisis. Los datos van en "
    "el primer argumento, que se llama y: pasa el data.frame en primera posición o como y=datos, "
    "nunca como x=datos, porque la llamada se detiene con el error el argumento no fue usado. "
    "La firma de ambas funciones es (y, varphi, se, test, complete, auxiliary, drop, silent). "
    "Como estimación "
    "convencional fija varphi=0, se=TRUE, test=TRUE y complete=TRUE tras definir los mismos casos "
    "completos para todas las comparaciones. Si se justifica una sensibilidad robusta, declara "
    "la tasa de atenuación de casos varphi elegida y separa sus resultados de los convencionales. "
    "Si se emplea complete=FALSE o auxiliary para analizar ausentes, documenta el método de la "
    "versión instalada y no mezcles muestras o métodos al comparar eliminaciones de ítems. "
    "Para las versiones estandarizadas vuelve a ajustar alpha y omega a ítems estandarizados "
    "con scale(), manteniendo nombres, claves y muestra; distingue ambos coeficientes de los "
    "obtenidos sobre ítems sin estandarizar. Extrae las estimaciones de ajuste$alpha o ajuste$omega, el error "
    "estándar con as.numeric(ajuste$se), y los contrastes de ajuste$fit si existen; comprueba names()/str() "
    "o consulta AYUDA: coefficientalpha::alpha si la estructura difiere. Presenta el contraste "
    "de tau-equivalencia para alfa y el de homogeneidad para omega, con F, grados de libertad "
    "y p cuando estén disponibles; no interpretes p>0,05 como demostración del supuesto. "
    "Construye IC Wald del 95 % con estimación ± qnorm(0.975)*SE y etiqueta el método; no los "
    "recortes artificialmente a 0–1. summary(objeto, type='raw', prob=0.95) imprime resultados "
    "pero no devuelve una tabla; su argumento type cambia el intervalo y no estandariza ítems. "
    "Si usas coefficientalpha::bootstrap, especifica type='alpha' u 'omega', alpha=0.95, "
    "nboot=1000, ci='bc', plot=FALSE, semilla y varphi coherentes con el ajuste, comprobando "
    "viabilidad y réplicas fallidas. Al eliminar ítems, suprime columnas y reajusta; drop designa "
    "filas de personas. Calcula la correlación ítem-resto sobre la misma muestra mediante R base. "
    "Recoge los campos numéricos en data.frames y preséntalos con tabla(); captura con capture.output() "
    "los mensajes de los ajustes para que no sustituyan las tablas ni impriman los datos individuales. "
    "Para ordinales identifica estos coeficientes como basados en puntuaciones observadas; "
    "reserva la matriz policórica y el modelo categórico para los coeficientes ordinales "
    "complementarios, sin atribuir a coefficientalpha una opción ordered o policórica no documentada. "
    "No atribuyas omega jerárquico a coefficientalpha::omega: usa un modelo específico solo si procede."
    " Las funciones de psych se escriben siempre con su prefijo, psych::polychoric y "
    "psych::fa.parallel, porque sin él el bloque se detiene con no se pudo encontrar la función, y "
    "solo aceptan los argumentos de su firma, comprobada en este intérprete. polychoric admite x, "
    "y, smooth, global, polycor, ML, std.err, weight, correct, progress, na.rm, delete y max.cat: "
    "max.observed.levels no existe y el tope de categorías por variable es max.cat, que vale 8 por "
    "omisión. fa.parallel admite x, n.obs, fm, fa, nfactors, main, n.iter, error.bars, se.bars, "
    "SMC, ylabel, show.legend, sim, quant, cor, use, plot, correct y sqrt: no hay verbose, la "
    "matriz policórica se pide con cor igual a poly, y plot igual a FALSE evita abrir un gráfico. "
    "Tampoco existe un argumento poly para el alfa: el alfa ordinal se obtiene de la matriz "
    "policórica y se declara como tal, separado del alfa de las puntuaciones observadas. "
    "Cualquier otro argumento inventado cuesta una ejecución de las seis: si dudas de una firma, "
    "responde AYUDA: psych::fa.parallel antes de probar."
)
for name in ("Fiabilidad", "Consistencia interna"):
    TEMPLATES[name] += RELIABILITY_METHOD
DESIGN_CODING = (
    " Codificación del diseño. Ninguna variable nominal entra en el modelo como número: "
    "conviértela con factor(), declara el orden de sus niveles y usa codificación tipo "
    "indicador, es decir contrastes de tratamiento con contr.treatment, que es la opción por "
    "omisión de R. La categoría de referencia es la primera categoría de la variable, el primer "
    "nivel que produce factor() con el orden natural de los valores; declárala explícitamente "
    "en los resultados y no la cambies sin decirlo. Una variable con k categorías aporta k-1 "
    "variables indicadoras: nómbralas de forma legible como variable_categoria, informa del n "
    "de cada categoría y comprueba que ninguna quede vacía ni con muy pocos casos; si ocurre, "
    "dilo y valora agrupar categorías antes de modelar, nunca en silencio. No interpretes el "
    "coeficiente de una sola indicadora como el efecto de la variable completa: contrasta sus "
    "k-1 indicadoras a la vez comparando modelos anidados ajustados exactamente a los mismos "
    "casos, con F parcial en modelos lineales y razón de verosimilitudes en los generalizados, "
    "e informa estadístico, grados de libertad y p. Las variables binarias llegan ya "
    "recodificadas a 0 y 1 por la aplicación, con su primera categoría como 0 y por tanto como "
    "referencia; consulta en el diccionario qué categoría corresponde a cada código y declara "
    "qué significa el valor 1 antes de interpretar el signo de su coeficiente. Trata una "
    "variable nominal de dos categorías igual que una binaria. Mantén una variable ordinal como "
    "número solo si la pregunta asume una relación lineal con sus códigos, declara ese supuesto "
    "y, si no se sostiene, trátala como factor con la misma codificación indicadora. "
    "Comprueba el rango de la matriz de diseño después de crear las indicadoras y, si hay "
    "colinealidad perfecta por categorías redundantes, identifica las variables implicadas en "
    "lugar de presentar coeficientes no estimables."
)
for name in ("ANCOVA", "Análisis de supervivencia", "Moderación", "Modelo multinivel",
             "Regresión", "Regresión logística", "Regresión multinomial", "Regresión ordinal",
             "Regresión para recuentos"):
    TEMPLATES[name] += DESIGN_CODING
LAVAAN_ROWS = (
    " Al leer lavaan::parameterEstimates o standardizedSolution, filtra las filas por lo que son y "
    "no supongas que hay una por indicador: las filas con op igual a ~~ y lhs igual a rhs incluyen "
    "las varianzas de los indicadores y además la de cada variable latente, de modo que con k "
    "indicadores y un factor salen k+1 y cualquier data.frame que las combine con las k cargas se "
    "detiene con el error los argumentos implican un número diferente de filas. Selecciona las "
    "varianzas de error exigiendo que lhs esté entre los nombres de los indicadores, empareja cada "
    "carga con la varianza del mismo indicador por nombre y no por posición, y comprueba la longitud "
    "de los vectores antes de construir la tabla."
    " El paquete no está adjunto: escribe el prefijo lavaan:: en todas sus funciones, también en sem, "
    "cfa, growth y lavaanify, porque sem a secas detiene el bloque con no se pudo encontrar la "
    "función. Y como el ajuste es un objeto S4 cuyos métodos no se registran sin adjuntar el "
    "paquete, no le apliques las genéricas de R: nobs falla con no 'nobs' method is available y coef "
    "con $ operator not defined for this S4 class. Usa lavaan::lavInspect(ajuste, 'ntotal') para el "
    "n analizado, lavaan::parameterEstimates y lavaan::standardizedSolution para las estimaciones, "
    "lavaan::fitMeasures para el ajuste y lavaan::lavInspect(ajuste, 'converged') para la "
    "convergencia. Tampoco leas slots internos como ajuste@boot, que puede venir vacío y deja "
    "cualquier if con el error argumento tiene longitud cero: la matriz de réplicas válidas es "
    "lavaan::lavInspect(ajuste, 'boot'), su nrow son las réplicas conservadas y sus atributos "
    "error.idx y nonadmissible identifican las fallidas; declara las réplicas pedidas y las "
    "conservadas por separado."
    " El argumento what de lavInspect solo admite unos pocos nombres: usa ntotal, nobs, converged, "
    "theta, rsquare, est, free y boot, y ninguno más, porque cualquier otro, por razonable que "
    "parezca, detiene el bloque con what argument unknown; residual.var no existe. Las varianzas "
    "residuales se leen de parameterEstimates con subset(pe, op == '~~' & lhs == rhs), que además "
    "trae su error estándar, o de la matriz theta, y la varianza explicada de cada ecuación es "
    "rsquare. Ante cualquier duda sobre un argumento de lavaan, consulta su ayuda respondiendo "
    "AYUDA: lavaan::lavInspect en vez de probar un nombre inventado, que cuesta una ejecución."
    " lavaan::fitMeasures devuelve un vector numérico con nombres, no una tabla: as.data.frame() "
    "sobre él produce una sola columna y asignarle después los nombres de los índices detiene el "
    "bloque con names attribute must be the same length as the vector. Construye la tabla "
    "siempre así: data.frame(Indice = names(fm), Valor = as.numeric(fm), row.names = NULL). Con "
    "estimadores robustos como WLSMV o MLR los índices escalados conservan el punto en su nombre, "
    "chisq.scaled, df.scaled, pvalue.scaled, cfi.scaled, tli.scaled y rmsea.scaled, y existen "
    "además cfi.robust, tli.robust y rmsea.robust; srmr no tiene versión escalada, así que pedir "
    "srmr.scaled avisa de unknown fit measure y devuelve un valor vacío que rompe la tabla. "
    "El número de parámetros libres es lavaan::fitMeasures(ajuste, 'npar'), un número con nombre; "
    "lavInspect con free devuelve una lista de matrices y pasarla a cat detiene el bloque con el "
    "argumento no es soportado por 'cat'. Envuelve en as.numeric() o unname() todo lo que imprimas "
    "con cat, que solo acepta vectores atómicos."
    " Comprobado también: semTools::compRelSEM con simplify igual a TRUE devuelve un vector sin "
    "nombres, así que names() sobre él es NULL y la tabla se detiene con los argumentos implican un "
    "número diferente de filas: 0, 1. Llámalo con simplify igual a FALSE, que devuelve una lista "
    "con el nombre de cada latente, o escribe tú los nombres de las latentes que declaraste. En "
    "general, no construyas una columna a partir de names() de un resultado sin comprobar antes "
    "que no es NULL. Y si el modelo tiene una sola variable latente no hay pares que comparar: "
    "di que la validez discriminante y el HTMT no son aplicables en vez de construir una tabla "
    "vacía."
)
for name in ("Análisis factorial confirmatorio", "Consistencia interna",
             "Invarianza de medida", "Mediación"):
    TEMPLATES[name] += LAVAAN_ROWS
MVN_CALL = (
    " Sobre MVN, versión 6.3 instalada en este equipo: su única interfaz es MVN::mvn y sus "
    "argumentos son exactamente data, subset, mvn_test, use_population, tol, alpha, outlier_seed, "
    "scale, descriptives, transform, impute, bootstrap, B, cores, univariate_test, "
    "multivariate_outlier_method, power_family, power_transform_type, show_new_data y tidy. "
    "Cualquier otro nombre detiene el bloque con el error los argumentos no fueron usados: en "
    "concreto no existen mvnMethod, multivariateNorm, univariateTest, multivariatePlot, desc ni "
    "mvnTest, que son de versiones antiguas del paquete. Una llamada devuelve una sola prueba "
    "multivariante, la de mvn_test, y una sola univariante, la de univariate_test, así que "
    "invócala una vez por "
    "prueba con mvn_test igual a su código, que puede ser mardia, hz, hw, royston, doornik_hansen "
    "o energy, pasando solo el data.frame y mvn_test. Los códigos univariantes son SW, SF, AD, CVM "
    "y Lillie. El data.frame debe contener solo columnas numéricas: filtra antes con "
    "Filter(is.numeric, dat) o selecciona las columnas por nombre. Lee el componente "
    "multivariate_normality, cuyas columnas son Test, "
    "Statistic, p.value, Method y MVN con esas mayúsculas, más df solo en Doornik-Hansen. La "
    "llamada con mardia devuelve dos filas, asimetría y curtosis, y cada una de las demás pruebas "
    "una sola: no escribas a mano un vector con los nombres de las pruebas, porque en cuanto no "
    "coincide con las filas devueltas el bloque se detiene con los argumentos implican un número "
    "diferente de filas. Y como Doornik-Hansen devuelve además la columna df y las demás pruebas "
    "no, no pases los componentes tal cual a do.call(rbind, ...): se detiene con el número de "
    "columnas de los argumentos no coincide. Construye en cada prueba un data.frame con las "
    "mismas columnas, por ejemplo Prueba, Estadistico, p y Metodo, y deja los grados de libertad "
    "en una columna de texto que escribas tú siempre. Combina después con do.call(rbind, ...) y "
    "toma los nombres de la columna "
    "Test. El p.value es texto y puede llegar como <0.001: límpialo con "
    "sub('>', '', sub('<', '', trimws(as.character(p.value)))) antes de compararlo con alfa. El "
    "componente univariate_normality trae Test, Variable, Statistic, p.value y Normality, sin "
    "Method y sin MVN."
)
for name in ("Análisis factorial confirmatorio", "Invarianza de medida"):
    TEMPLATES[name] += MVN_CALL
SEMTOOLS_CALL = (
    " Sobre semTools, versión 0.5.10 instalada en este equipo: semTools::htmt recibe como primer "
    "argumento la sintaxis del modelo de medida de lavaan, no el data.frame ni una lista de "
    "grupos de ítems, y los datos van en data. Sus argumentos son model, data, sample.cov, "
    "missing, ordered, absolute y htmt2, y ninguno más: no existe method, y pasar los datos en "
    "primera posición hace que lavaan intente leerlos como modelo y detiene el bloque con formula "
    "without valid operator. Por omisión htmt2 vale TRUE y devuelve el HTMT2, la media "
    "geométrica, mientras que htmt2 igual a FALSE devuelve el HTMT clásico, la media aritmética: "
    "para presentar los dos, llama dos veces al mismo modelo cambiando solo ese argumento. Con "
    "indicadores ordinales declara ordered con sus nombres. Devuelve una matriz triangular sin "
    "intervalos de confianza: si te piden intervalos, obtenlos remuestreando casos con una "
    "semilla declarada y recalculando el HTMT en cada réplica, e informa del número de réplicas, "
    "o di que el paquete no los proporciona. La fiabilidad compuesta es "
    "semTools::compRelSEM(ajuste), con tau.eq igual a TRUE si quieres el alfa, y la varianza "
    "media extraída es semTools::AVE(ajuste); ambas se calculan sobre el ajuste de lavaan, no "
    "sobre los datos. Comprobado también sobre un modelo de segundo orden: AVE devuelve un "
    "vector numérico con el nombre de cada factor de primer orden y ninguno más, de modo que se "
    "indexa con una sola dimensión, ave de los nombres, y escribir dos índices detiene el bloque "
    "con número incorreto de dimensiones. compRelSEM devuelve una lista con un elemento por "
    "factor, cada uno con texto explicativo alrededor del número: conviértelo con unlist() o con "
    "as.numeric(), o pasa simplify igual a TRUE, que devuelve un vector sin nombres a los que "
    "tendrás que poner tú los de los factores. No pases higher, que está obsoleto: los factores "
    "de orden superior se detectan solos. Y htmt solo admite el modelo de medida de primer "
    "orden: si tu sintaxis incluye el factor de segundo orden, quita esa línea antes de llamarlo "
    "o se detiene con Missing observed variables in the dataset seguido de los nombres de los "
    "factores. Antes de montar una tabla con varios de estos resultados, comprueba que todos "
    "tienen la misma longitud, porque el factor de segundo orden aparece en unos y no en otros. "
    "Con indicadores declarados como ordinales, es decir con ordered y WLSMV, compRelSEM con "
    "tau.eq igual a TRUE se detiene porque el alfa pedido sería el de la escala ordinal "
    "observada y no el de la escala latente: para el alfa en esa situación añade ord.scale igual "
    "a FALSE, declarando que es el alfa sobre la respuesta latente continua, y deja el omega en "
    "la escala observada con ord.scale igual a TRUE, que es el valor por omisión. Explica esa "
    "diferencia al presentarlos juntos en lugar de mezclar las dos escalas en una sola columna. "
    "Esta es la forma correcta de montar la tabla de fiabilidad y validez convergente, "
    "comprobada con WLSMV y un modelo de segundo orden; imítala: "
    "om <- unlist(semTools::compRelSEM(ajuste)); "
    "al <- unlist(semTools::compRelSEM(ajuste, tau.eq = TRUE, ord.scale = FALSE)); "
    "ave <- semTools::AVE(ajuste); "
    "df_om <- data.frame(Factor = names(om), Omega = round(as.numeric(om), 3)); "
    "df_al <- data.frame(Factor = names(al), Alfa = round(as.numeric(al), 3)); "
    "df_ave <- data.frame(Factor = names(ave), AVE = round(as.numeric(ave), 3)); "
    "tabla(merge(merge(df_om, df_al, by = 'Factor'), df_ave, by = 'Factor')). Une por nombre con "
    "merge y no por posición. Cada elemento de la lista que devuelve compRelSEM es un número con "
    "atributos, no una lista: pedirle x$omega detiene el bloque con el operador $ no es válido "
    "para vectores atómicos, y basta unlist() o as.numeric(). Con esta receta omega y alfa salen "
    "siempre, también con WLSMV e indicadores ordinales, así que no escribas que el paquete o el "
    "estimador no permiten calcularlos ni presentes una columna de NA: si te salen NA es que los "
    "has extraído mal, vuelve a intentarlo con estas líneas."
)
for name in ("Análisis factorial confirmatorio", "Consistencia interna",
             "Invarianza de medida", "Fiabilidad"):
    TEMPLATES[name] += SEMTOOLS_CALL
TEMPLATES = {name: prompt + (
    " En todos los cálculos documenta ausentes, n efectivo y exclusiones, sin imputar ni recodificar "
    "silenciosamente. Salvo hipótesis direccional previa, usa contrastes bilaterales, alfa=0,05 e "
    "IC del 95 %. Shapiro–Wilk solo es aplicable con entre 3 y 5000 valores finitos y no constantes; "
    "no tomes una submuestra arbitraria para obtener un p ni interpretes p>0,05 como prueba de normalidad. "
    "No reimplementes a mano lo que R ya hace: usa p.adjust para los ajustes por comparaciones "
    "múltiples, y en general la función del paquete en vez de reescribir su algoritmo. Mantén cada "
    "bloque de R centrado y corto; un bloque larguísimo agota el límite de salida y llega truncado. "
    "Reparte el análisis en varios bloques si hace falta: puedes enviar un bloque nuevo después de "
    "recibir la salida del anterior, y así hasta completar todo lo pedido. Ninguna prueba solicitada "
    "puede quedar sin ejecutar: no escribas que algo queda pendiente, no calculado o para una salida "
    "posterior, porque nadie va a pedirlo después. Si una prueba concreta no es estimable con estos "
    "datos, dilo con su motivo técnico, y calcula todas las demás. "
    "Muchas funciones de R devuelven un vector con nombres, no una tabla. Para pasarlo a tabla "
    "usa siempre data.frame(Indice = names(x), Valor = as.numeric(x), row.names = NULL): "
    "as.data.frame() sobre un vector con nombres crea una sola columna y asignarle después los "
    "nombres del vector detiene el bloque con names attribute must be the same length as the "
    "vector. Comprueba la forma con str() o length() antes de combinar dos resultados en la "
    "misma tabla. "
    "Antes de redondear, promediar o comparar, comprueba que la columna es numérica: round() o "
    "mean() sobre texto detienen el bloque con argumento no numérico para una función matemática, "
    "y varias columnas que R devuelve como p, gl o conclusiones son cadenas. "
    "No crees un objeto por grupo con nombres numerados tipo desc_g1, desc_g2: recorre los niveles "
    "observados con split() o con lapply() sobre levels(factor(variable)) y combina las filas con "
    "do.call(rbind, ...), porque en cuanto hay más niveles de los que escribiste a mano el bloque "
    "se detiene con el error objeto no encontrado. "
    "Los datos ya están cargados en el data.frame dat, con las variables seleccionadas: úsalo "
    "tal cual y no inventes otro nombre como datos o df, porque no existen y el bloque falla "
    "en la primera línea. Para un subconjunto, derívalo de dat en el propio bloque. "
    "No escribas nunca install.packages() ni library() de un paquete ausente, ni siquiera dentro "
    "de un if o tras un requireNamespace(): la aplicación rechaza el bloque completo por tocar el "
    "sistema y no ejecuta nada, y ese rechazo no significa que el paquete falte. Comprueba la "
    "disponibilidad solo con requireNamespace(nombre, quietly=TRUE) y fíate de la lista de paquetes "
    "instalados que recibes en el contexto. "
    "Ninguna decisión del código puede depender de un valor que pueda ser NA: compruébalo con "
    "is.na() o envuelve la condición en isTRUE(), porque un if con NA detiene la ejecución; si una "
    "comprobación no es evaluable, informa del motivo y sigue con la opción por omisión declarada. "
    "Usa funciones de R base o paquetes instalados; si falta una dependencia o un estadístico no es "
    "estimable, indícalo sin inventar cifras ni sustituir silenciosamente el método. Presenta resultados "
    "y diagnósticos en tablas tipo Word, separando estimaciones, contrastes y conclusiones. Incluye "
    "interpretación estadística y sustantiva basada únicamente en lo calculado: hipótesis, dirección, "
    "magnitud, precisión y limitaciones. Si la salida permanece local, incorpora al código R un resumen "
    "interpretativo que se construya a partir de los resultados calculados; no afirmes haber visto una "
    "salida que no recibiste. No inventes relevancia clínica o práctica sin un umbral definido por el usuario."
) for name, prompt in sorted(TEMPLATES.items(), key=lambda item: unicodedata.normalize("NFKD", item[0]).casefold())}
# Bibliografía por procedimiento. Lista cerrada: el modelo cita de aquí y no inventa.
# Sin comillas dobles ni corchetes, que romperían el relleno de la consulta.
REFERENCIAS = {
    "ANCOVA": [
        "Maxwell, S. E., Delaney, H. D., y Kelley, K. (2018). Designing experiments and analyzing data: A model comparison perspective (3.ª ed.). Routledge.",
        "Fox, J., y Weisberg, S. (2019). An R companion to applied regression (3.ª ed.). Sage.",
        "Lenth, R. V. (2024). emmeans: Estimated marginal means, aka least-squares means. Paquete de R. https://rvlenth.github.io/emmeans/",
    ],
    "ANOVA": [
        "Maxwell, S. E., Delaney, H. D., y Kelley, K. (2018). Designing experiments and analyzing data: A model comparison perspective (3.ª ed.). Routledge.",
        "Delacre, M., Lakens, D., y Leys, C. (2017). Why psychologists should by default use Welch t-test instead of Student t-test. International Review of Social Psychology, 30(1), 92-101. https://doi.org/10.5334/irsp.82",
        "Lakens, D. (2013). Calculating and reporting effect sizes to facilitate cumulative science. Frontiers in Psychology, 4, 863. https://doi.org/10.3389/fpsyg.2013.00863",
    ],
    "ANOVA de medidas repetidas": [
        "Maxwell, S. E., Delaney, H. D., y Kelley, K. (2018). Designing experiments and analyzing data: A model comparison perspective (3.ª ed.). Routledge.",
        "Singmann, H., Bolker, B., Westfall, J., Aust, F., y Ben-Shachar, M. S. (2024). afex: Analysis of factorial experiments. Paquete de R. https://afex.singmann.science/",
        "Lakens, D. (2013). Calculating and reporting effect sizes to facilitate cumulative science. Frontiers in Psychology, 4, 863. https://doi.org/10.3389/fpsyg.2013.00863",
    ],
    "Acuerdo entre evaluaciones": [
        "Gwet, K. L. (2014). Handbook of inter-rater reliability (4.ª ed.). Advanced Analytics.",
        "Koo, T. K., y Li, M. Y. (2016). A guideline of selecting and reporting intraclass correlation coefficients for reliability research. Journal of Chiropractic Medicine, 15(2), 155-163. https://doi.org/10.1016/j.jcm.2016.02.012",
        "McHugh, M. L. (2012). Interrater reliability: The kappa statistic. Biochemia Medica, 22(3), 276-282. https://doi.org/10.11613/BM.2012.031",
    ],
    "Análisis clúster": [
        "Kaufman, L., y Rousseeuw, P. J. (2005). Finding groups in data: An introduction to cluster analysis. Wiley.",
        "Everitt, B. S., Landau, S., Leese, M., y Stahl, D. (2011). Cluster analysis (5.ª ed.). Wiley.",
        "Hennig, C., Meila, M., Murtagh, F., y Rocci, R. (Eds.). (2015). Handbook of cluster analysis. Chapman and Hall/CRC.",
    ],
    "Análisis de supervivencia": [
        "Therneau, T. M., y Grambsch, P. M. (2000). Modeling survival data: Extending the Cox model. Springer.",
        "Kleinbaum, D. G., y Klein, M. (2012). Survival analysis: A self-learning text (3.ª ed.). Springer.",
        "Moore, D. F. (2016). Applied survival analysis using R. Springer.",
    ],
    "Análisis discriminante": [
        "Tabachnick, B. G., y Fidell, L. S. (2019). Using multivariate statistics (7.ª ed.). Pearson.",
        "Hastie, T., Tibshirani, R., y Friedman, J. (2009). The elements of statistical learning (2.ª ed.). Springer. Libre en https://hastie.su.domains/ElemStatLearn/",
        "Venables, W. N., y Ripley, B. D. (2002). Modern applied statistics with S (4.ª ed.). Springer.",
    ],
    "Análisis factorial confirmatorio": [
        "Brown, T. A. (2015). Confirmatory factor analysis for applied research (2.ª ed.). Guilford Press.",
        "Kline, R. B. (2023). Principles and practice of structural equation modeling (5.ª ed.). Guilford Press.",
        "Rosseel, Y. (2012). lavaan: An R package for structural equation modeling. Journal of Statistical Software, 48(2), 1-36. https://doi.org/10.18637/jss.v048.i02",
        "Hu, L., y Bentler, P. M. (1999). Cutoff criteria for fit indexes in covariance structure analysis. Structural Equation Modeling, 6(1), 1-55. https://doi.org/10.1080/10705519909540118",
        "Fornell, C., y Larcker, D. F. (1981). Evaluating structural equation models with unobservable variables and measurement error. Journal of Marketing Research, 18(1), 39-50. https://doi.org/10.1177/002224378101800104",
        "Henseler, J., Ringle, C. M., y Sarstedt, M. (2015). A new criterion for assessing discriminant validity in variance-based structural equation modeling. Journal of the Academy of Marketing Science, 43(1), 115-135. https://doi.org/10.1007/s11747-014-0403-8",
        "Hair, J. F., Black, W. C., Babin, B. J., y Anderson, R. E. (2019). Multivariate data analysis (8.ª ed.). Cengage.",
    ],
    "Análisis factorial exploratorio": [
        "Watkins, M. W. (2021). A step-by-step guide to exploratory factor analysis with R and RStudio. Routledge.",
        "Fabrigar, L. R., y Wegener, D. T. (2012). Exploratory factor analysis. Oxford University Press.",
        "Flora, D. B., y Flake, J. K. (2017). The purpose and practice of exploratory and confirmatory factor analysis in psychological research. Canadian Journal of Behavioural Science, 49(2), 78-88. https://doi.org/10.1037/cbs0000069",
        "Revelle, W. (2024). psych: Procedures for psychological, psychometric and personality research. Paquete de R. https://personality-project.org/r/psych/",
    ],
    "Antes y después": [
        "Maxwell, S. E., Delaney, H. D., y Kelley, K. (2018). Designing experiments and analyzing data: A model comparison perspective (3.ª ed.). Routledge.",
        "Lakens, D. (2013). Calculating and reporting effect sizes to facilitate cumulative science. Frontiers in Psychology, 4, 863. https://doi.org/10.3389/fpsyg.2013.00863",
        "Cumming, G. (2014). The new statistics: Why and how. Psychological Science, 25(1), 7-29. https://doi.org/10.1177/0956797613504966",
    ],
    "Ausentes e imputación múltiple": [
        "van Buuren, S. (2018). Flexible imputation of missing data (2.ª ed.). Chapman and Hall/CRC. Libre en https://stefvanbuuren.name/fimd/",
        "van Buuren, S., y Groothuis-Oudshoorn, K. (2011). mice: Multivariate imputation by chained equations in R. Journal of Statistical Software, 45(3), 1-67. https://doi.org/10.18637/jss.v045.i03",
        "Enders, C. K. (2022). Applied missing data analysis (2.ª ed.). Guilford Press.",
    ],
    "Consistencia interna": [
        "McNeish, D. (2018). Thanks coefficient alpha, we will take it from here. Psychological Methods, 23(3), 412-433. https://doi.org/10.1037/met0000144",
        "Revelle, W., y Condon, D. M. (2019). Reliability from alpha to omega: A tutorial. Psychological Assessment, 31(12), 1395-1411. https://doi.org/10.1037/pas0000754",
        "Zhang, Z., y Yuan, K.-H. (2016). Robust coefficients alpha and omega and confidence intervals with outlying observations and missing data. Educational and Psychological Measurement, 76(3), 387-411. https://doi.org/10.1177/0013164415594658",
        "Dunn, T. J., Baguley, T., y Brunsden, V. (2014). From alpha to omega: A practical solution to the pervasive problem of internal consistency estimation. British Journal of Psychology, 105(3), 399-412. https://doi.org/10.1111/bjop.12046",
    ],
    "Correlación": [
        "Cohen, J. (1988). Statistical power analysis for the behavioral sciences (2.ª ed.). Erlbaum.",
        "Bishara, A. J., y Hittner, J. B. (2012). Testing the significance of a correlation with nonnormal data. Psychological Methods, 17(3), 399-417. https://doi.org/10.1037/a0028087",
        "Schober, P., Boer, C., y Schwarte, L. A. (2018). Correlation coefficients: Appropriate use and interpretation. Anesthesia and Analgesia, 126(5), 1763-1768. https://doi.org/10.1213/ANE.0000000000002864",
    ],
    "Curva ROC y capacidad diagnóstica": [
        "Robin, X., Turck, N., Hainard, A., Tiberti, N., Lisacek, F., Sanchez, J.-C., y Müller, M. (2011). pROC: An open-source package for R and S+ to analyze and compare ROC curves. BMC Bioinformatics, 12, 77. https://doi.org/10.1186/1471-2105-12-77",
        "Pepe, M. S. (2003). The statistical evaluation of medical tests for classification and prediction. Oxford University Press.",
        "DeLong, E. R., DeLong, D. M., y Clarke-Pearson, D. L. (1988). Comparing the areas under two or more correlated receiver operating characteristic curves. Biometrics, 44(3), 837-845. https://doi.org/10.2307/2531595",
    ],
    "Descriptivos": [
        "Wickham, H., Çetinkaya-Rundel, M., y Grolemund, G. (2023). R for data science (2.ª ed.). O Reilly. Libre en https://r4ds.hadley.nz/",
        "Thulin, M. (2024). Modern statistics with R (2.ª ed.). Chapman and Hall/CRC. Libre en https://www.modernstatisticswithr.com/",
        "Tukey, J. W. (1977). Exploratory data analysis. Addison-Wesley.",
    ],
    "Diferencia entre medias": [
        "Delacre, M., Lakens, D., y Leys, C. (2017). Why psychologists should by default use Welch t-test instead of Student t-test. International Review of Social Psychology, 30(1), 92-101. https://doi.org/10.5334/irsp.82",
        "Lakens, D. (2013). Calculating and reporting effect sizes to facilitate cumulative science. Frontiers in Psychology, 4, 863. https://doi.org/10.3389/fpsyg.2013.00863",
        "Maxwell, S. E., Delaney, H. D., y Kelley, K. (2018). Designing experiments and analyzing data: A model comparison perspective (3.ª ed.). Routledge.",
    ],
    "Fiabilidad": [
        "McNeish, D. (2018). Thanks coefficient alpha, we will take it from here. Psychological Methods, 23(3), 412-433. https://doi.org/10.1037/met0000144",
        "Revelle, W., y Condon, D. M. (2019). Reliability from alpha to omega: A tutorial. Psychological Assessment, 31(12), 1395-1411. https://doi.org/10.1037/pas0000754",
        "Zhang, Z., y Yuan, K.-H. (2016). Robust coefficients alpha and omega and confidence intervals with outlying observations and missing data. Educational and Psychological Measurement, 76(3), 387-411. https://doi.org/10.1177/0013164415594658",
    ],
    "Invarianza de medida": [
        "Putnick, D. L., y Bornstein, M. H. (2016). Measurement invariance conventions and reporting: The state of the art and future directions for psychological research. Developmental Review, 41, 71-90. https://doi.org/10.1016/j.dr.2016.06.004",
        "Cheung, G. W., y Rensvold, R. B. (2002). Evaluating goodness-of-fit indexes for testing measurement invariance. Structural Equation Modeling, 9(2), 233-255. https://doi.org/10.1207/S15328007SEM0902_5",
        "Chen, F. F. (2007). Sensitivity of goodness of fit indexes to lack of measurement invariance. Structural Equation Modeling, 14(3), 464-504. https://doi.org/10.1080/10705510701301834",
        "Kline, R. B. (2023). Principles and practice of structural equation modeling (5.ª ed.). Guilford Press.",
    ],
    "Mediación": [
        "Hayes, A. F. (2022). Introduction to mediation, moderation, and conditional process analysis (3.ª ed.). Guilford Press.",
        "MacKinnon, D. P. (2008). Introduction to statistical mediation analysis. Erlbaum.",
        "Preacher, K. J., y Hayes, A. F. (2008). Asymptotic and resampling strategies for assessing and comparing indirect effects in multiple mediator models. Behavior Research Methods, 40(3), 879-891. https://doi.org/10.3758/BRM.40.3.879",
        "VanderWeele, T. J. (2015). Explanation in causal inference: Methods for mediation and interaction. Oxford University Press.",
    ],
    "Modelo multinivel": [
        "Hox, J. J., Moerbeek, M., y van de Schoot, R. (2018). Multilevel analysis: Techniques and applications (3.ª ed.). Routledge.",
        "Snijders, T. A. B., y Bosker, R. J. (2012). Multilevel analysis: An introduction to basic and advanced multilevel modeling (2.ª ed.). Sage.",
        "Bates, D., Mächler, M., Bolker, B., y Walker, S. (2015). Fitting linear mixed-effects models using lme4. Journal of Statistical Software, 67(1), 1-48. https://doi.org/10.18637/jss.v067.i01",
        "Kuznetsova, A., Brockhoff, P. B., y Christensen, R. H. B. (2017). lmerTest package: Tests in linear mixed effects models. Journal of Statistical Software, 82(13), 1-26. https://doi.org/10.18637/jss.v082.i13",
    ],
    "Moderación": [
        "Hayes, A. F. (2022). Introduction to mediation, moderation, and conditional process analysis (3.ª ed.). Guilford Press.",
        "Aiken, L. S., y West, S. G. (1991). Multiple regression: Testing and interpreting interactions. Sage.",
        "Cohen, J., Cohen, P., West, S. G., y Aiken, L. S. (2003). Applied multiple regression/correlation analysis for the behavioral sciences (3.ª ed.). Erlbaum.",
    ],
    "Normalidad": [
        "Thode, H. C. (2002). Testing for normality. Marcel Dekker.",
        "Korkmaz, S., Goksuluk, D., y Zararsiz, G. (2014). MVN: An R package for assessing multivariate normality. The R Journal, 6(2), 151-162. https://doi.org/10.32614/RJ-2014-031",
        "Mardia, K. V. (1970). Measures of multivariate skewness and kurtosis with applications. Biometrika, 57(3), 519-530. https://doi.org/10.1093/biomet/57.3.519",
        "Henze, N., y Zirkler, B. (1990). A class of invariant consistent tests for multivariate normality. Communications in Statistics - Theory and Methods, 19(10), 3595-3617. https://doi.org/10.1080/03610929008830400",
    ],
    "Regresión": [
        "Fox, J. (2016). Applied regression analysis and generalized linear models (3.ª ed.). Sage.",
        "Fox, J., y Weisberg, S. (2019). An R companion to applied regression (3.ª ed.). Sage.",
        "Harrell, F. E. (2015). Regression modeling strategies (2.ª ed.). Springer.",
        "Gelman, A., Hill, J., y Vehtari, A. (2020). Regression and other stories. Cambridge University Press. Materiales libres en https://avehtari.github.io/ROS-Examples/",
    ],
    "Regresión logística": [
        "Hosmer, D. W., Lemeshow, S., y Sturdivant, R. X. (2013). Applied logistic regression (3.ª ed.). Wiley.",
        "Agresti, A. (2019). An introduction to categorical data analysis (3.ª ed.). Wiley.",
        "Harrell, F. E. (2015). Regression modeling strategies (2.ª ed.). Springer.",
        "Steyerberg, E. W. (2019). Clinical prediction models (2.ª ed.). Springer.",
    ],
    "Regresión multinomial": [
        "Agresti, A. (2013). Categorical data analysis (3.ª ed.). Wiley.",
        "Venables, W. N., y Ripley, B. D. (2002). Modern applied statistics with S (4.ª ed.). Springer.",
        "Hosmer, D. W., Lemeshow, S., y Sturdivant, R. X. (2013). Applied logistic regression (3.ª ed.). Wiley.",
    ],
    "Regresión ordinal": [
        "Agresti, A. (2010). Analysis of ordinal categorical data (2.ª ed.). Wiley.",
        "Bürkner, P.-C., y Vuorre, M. (2019). Ordinal regression models in psychology: A tutorial. Advances in Methods and Practices in Psychological Science, 2(1), 77-101. https://doi.org/10.1177/2515245918823199",
        "Christensen, R. H. B. (2023). ordinal: Regression models for ordinal data. Paquete de R. https://cran.r-project.org/package=ordinal",
    ],
    "Regresión para recuentos": [
        "Cameron, A. C., y Trivedi, P. K. (2013). Regression analysis of count data (2.ª ed.). Cambridge University Press.",
        "Hilbe, J. M. (2014). Modeling count data. Cambridge University Press.",
        "Zeileis, A., Kleiber, C., y Jackman, S. (2008). Regression models for count data in R. Journal of Statistical Software, 27(8), 1-25. https://doi.org/10.18637/jss.v027.i08",
    ],
    "Tablas de contingencia": [
        "Agresti, A. (2019). An introduction to categorical data analysis (3.ª ed.). Wiley.",
        "Agresti, A. (2013). Categorical data analysis (3.ª ed.). Wiley.",
        "Fleiss, J. L., Levin, B., y Paik, M. C. (2003). Statistical methods for rates and proportions (3.ª ed.). Wiley.",
    ],
}
CITAS = (
    " Cierra siempre la respuesta con una sección final titulada Referencias, después de la "
    "interpretación, con la lista de obras que figura a continuación, copiadas tal cual, una por "
    "línea de lista y ordenadas alfabéticamente. Cita en el texto, con autor y año, las que "
    "respalden cada decisión metodológica que tomes, por ejemplo el criterio de un índice de "
    "ajuste, la elección de un estimador o la lectura de un tamaño del efecto. No añadas ninguna "
    "obra que no esté en la lista, no inventes autores, años, páginas ni DOI, y no cites de "
    "memoria: si necesitas apoyar algo que la lista no cubre, dilo en lugar de citarlo. Añade "
    "también R con la versión realmente usada, que obtienes imprimiendo R.version.string en tu "
    "bloque, con esta forma: R Core Team y el año de esa versión, R: A language and environment "
    "for statistical computing, R Foundation for Statistical Computing, Viena, "
    "https://www.R-project.org/. Estas son las obras que puedes citar, y ninguna más: "
)
TEMPLATES = {name: prompt + CITAS + " ".join(REFERENCIAS[name])
             for name, prompt in TEMPLATES.items()}
# Guías de API que se añaden al contexto cuando la consulta las necesita. Una consulta
# escrita a mano no lleva las reglas de ninguna plantilla, y sin ellas el modelo recurre a
# la API antigua del paquete y gasta sus ejecuciones en errores de argumento no usado.
# Cada entrada: qué pide la consulta, una marca que indica que ya las trae, y la guía.
GUIAS_API = (
    # AVE lleva delimitadores: sin ellos casaba dentro de clave y de grave.
    (re.compile(r"MVN|mardia|henze|royston|doornik|normalidad", re.I),
     "mvn_test", MVN_CALL),
    (re.compile(r"HTMT|validez discriminante|fiabilidad compuesta|varianza media extraída|"
                r"AVE|semTools", re.I),
     "semTools::htmt", SEMTOOLS_CALL),
    # Sin ecuaciones estructurales a secas: las plantillas la mencionan de pasada al hablar
    # de consecuencias, y la guía se colaba donde no se usa lavaan.
    (re.compile(r"lavaan|factorial confirmatorio|segundo orden|invarianza|"
                r"variables? latentes?|modelo de medida|sem\(|cfa\(", re.I),
     "lavaan::lavInspect", LAVAAN_ROWS),
)


def guias_necesarias(ask: str) -> list[str]:
    """Guías de uso de paquete que la consulta necesita y todavía no incluye."""
    return [guia for patron, marca, guia in GUIAS_API if patron.search(ask) and marca not in ask]


# Funciones que se documentan cuando la consulta nombra el paquete sin escribir pkg::fn.
# Las firmas no se escriben aquí: se leen del R instalado en cada consulta.
FUNCIONES_POR_TEMA = (
    (re.compile(r"\bMVN\b|normalidad multivariante|mardia|henze|royston|doornik", re.I),
     ("MVN::mvn",)),
    (re.compile(r"lavaan|factorial confirmatorio|segundo orden|invarianza|modelo de medida|"
                r"variables? latentes?", re.I),
     ("lavaan::sem", "lavaan::cfa", "lavaan::parameterEstimates", "lavaan::standardizedSolution",
      "lavaan::fitMeasures", "lavaan::lavInspect")),
    (re.compile(r"semTools|HTMT|validez discriminante|fiabilidad compuesta|\bAVE\b", re.I),
     ("semTools::htmt", "semTools::compRelSEM", "semTools::AVE")),
    (re.compile(r"\bpsych\b|análisis paralelo|policórica|alfa ordinal", re.I),
     ("psych::fa.parallel", "psych::polychoric", "psych::fa")),
)


# Bibliografía para consultas escritas a mano: se toma prestada de la plantilla del tema.
TEMAS_BIBLIO = (
    (re.compile(r"\bMVN\b|normalidad (?:multi|uni|bi)variante|mardia|henze", re.I), "Normalidad"),
    (re.compile(r"lavaan|factorial confirmatorio|segundo orden|modelo de medida|"
                r"ecuaciones estructurales", re.I), "Análisis factorial confirmatorio"),
    (re.compile(r"invarianza", re.I), "Invarianza de medida"),
    (re.compile(r"HTMT|\bAVE\b|fiabilidad|alfa de cronbach|omega|consistencia interna", re.I),
     "Consistencia interna"),
    (re.compile(r"mediaci[óo]n|efecto indirecto", re.I), "Mediación"),
    (re.compile(r"moderaci[óo]n|interacci[óo]n", re.I), "Moderación"),
    (re.compile(r"multinivel|efectos (?:mixtos|aleatorios)|lme4|lmer", re.I), "Modelo multinivel"),
    (re.compile(r"supervivencia|coxph|kaplan", re.I), "Análisis de supervivencia"),
    (re.compile(r"\bROC\b|sensibilidad y especificidad|curva ROC", re.I),
     "Curva ROC y capacidad diagnóstica"),
    (re.compile(r"cl[úu]ster|conglomerados|k-?means", re.I), "Análisis clúster"),
    (re.compile(r"imputaci[óo]n|\bmice\b|valores ausentes", re.I), "Ausentes e imputación múltiple"),
    (re.compile(r"regresi[óo]n log[íi]stica", re.I), "Regresión logística"),
    (re.compile(r"regresi[óo]n lineal|\blm\(|m[íi]nimos cuadrados", re.I), "Regresión"),
    (re.compile(r"\bANOVA\b", re.I), "ANOVA"),
    (re.compile(r"factorial exploratorio|\bEFA\b|análisis paralelo", re.I),
     "Análisis factorial exploratorio"),
    (re.compile(r"correlaci[óo]n", re.I), "Correlación"),
)
# shortcut: tres temas por consulta; subirlo alarga el contexto sin añadir precisión.
TEMAS_MAX = 3


def bibliografia_para(ask: str) -> list[str]:
    """Obras citables de los temas que toca una consulta escrita a mano."""
    obras, vistas = [], set()
    for patron, tema in TEMAS_BIBLIO:
        if len(vistas) >= TEMAS_MAX:
            break
        if patron.search(ask) and tema not in vistas:
            vistas.add(tema)
            obras.extend(o for o in REFERENCIAS[tema] if o not in obras)
    return obras


def funciones_a_documentar(ask: str) -> list[str]:
    """Funciones cuya firma real conviene leer antes de que el modelo escriba el código."""
    # El punto final de la frase se pega al nombre: stats::lm. no existe y gastaría una consulta.
    nombres = [f"{pkg}::{fn.rstrip('.')}"
               for pkg, fn in re.findall(r"\b([A-Za-z][\w.]*)::([\w.]+)", ask) if fn.strip(".")]
    for patron, funciones in FUNCIONES_POR_TEMA:
        if patron.search(ask):
            nombres.extend(funciones)
    return list(dict.fromkeys(nombres))


SYSTEM = """Eres el asistente estadístico de AnalizaR Desktop. Responde en español y Markdown.
Escribe las fórmulas estadísticas con símbolos Unicode legibles (μ, σ, ≠, ≤, H₀, R²),
sin delimitadores de matemáticas ni comandos LaTeX; conserva literalmente el código R.
Presenta resultados, descriptivos y comparaciones en tablas Markdown con encabezados
y separador | --- |. No dibujes tablas con caracteres ASCII ni las encierres en bloques
de código. Acompaña las tablas de una interpretación breve cuando corresponda.
Ayuda a plantear y realizar procedimientos estadísticos generales con R. Pide aclaraciones
si faltan variables, hipótesis o decisiones metodológicas. Nunca inventes resultados.
Los datos locales están en `dat`, un data.frame con las variables seleccionadas.
Cada bloque R se ejecuta en una sesión nueva: conserva `dat` y los ayudantes locales,
pero no los objetos ni paquetes cargados por bloques anteriores. Devuelve scripts
completos y autocontenidos; no dependas de ajustes creados en una ejecución previa.
Los nombres de variables son referencias a columnas, no observaciones. Si `vars`
es un vector de nombres, calcula sobre `dat[, vars, drop=FALSE]`, nunca sobre
`vars` directamente. Para descriptivos utiliza `descriptivos(dat[, vars, drop=FALSE])`
y presenta su resultado con `tabla()`. Esta función local calcula sobre las columnas
numéricas y señala las no numéricas sin convertir sus categorías a números.
Para calcular responde únicamente con un bloque ```r que imprima sus resultados.
Para imprimir resultados tabulares usa la función local `tabla(data.frame(...))` o
`tabla(matriz)`, ya disponible en la sesión. Conserva nombres, cifras y unidades.
No releas datos, no escribas archivos, no uses red, system(), setwd() ni install.packages().
Usa paquetes instalados; si dudas de una API imprime str()/names() o consulta su ayuda
respondiendo únicamente AYUDA: paquete::funcion. Explica supuestos y limitaciones.
Cuando recibas una salida de R, interpreta sólo esas cifras. Si falló puedes devolver
un bloque corregido. La respuesta final debe contener los resultados, sin narrar reparaciones.
Estos cálculos no tienen auditoría estadística automática.
"""


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def recent_data_files() -> list[Path]:
    try:
        values = json.loads((secrets.config_dir() / "recent_data.json").read_text(encoding="utf-8"))
        if not isinstance(values, list):
            return []
        return list(dict.fromkeys(Path(p).resolve() for p in values if isinstance(p, str)))[:5]
    except (OSError, ValueError):
        return []


def remember_data_file(path: Path) -> None:
    path = Path(path).resolve()
    recent = [path] + [p for p in recent_data_files() if p != path]
    target = secrets.config_dir() / "recent_data.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with temporary_file() as temporary:
        write_json(temporary, [str(p) for p in recent[:5]])
        replace_file(temporary, target)


def prepare_data(request: dict, folder: Path) -> dict:
    """Normaliza y transforma una copia, conservando los metadatos del origen."""
    source = Path(request["data"]).resolve()
    header, rows, meta = engine.read_table(source, folder)
    if not header or any(not name for name in header) or len(set(header)) != len(header):
        raise ValueError("Las columnas deben tener nombres únicos y no vacíos.")
    original = engine.phase1_profile(source, folder)
    recuperados = original.get("class_overrides")
    classes = {c["column"]: c["class"] for c in original["columns"]}
    classes.update(request.get("classes", {}))
    rows, recoding = engine.apply_recode(header, rows,
                                        engine.parse_recode(request.get("recode", "")))
    collapsing = []
    minimum = request.get("collapse", 0)
    if minimum:
        ordinal = [name for name in header if classes.get(name) == "ordinal"]
        rows, collapsing = engine.collapse_rare_categories(header, rows, ordinal, minimum)
    binarias = [name for name in header if classes.get(name) == "binary"]
    rows, binarizing, codebook = engine.binarize(header, rows, binarias, meta.get("codebook", {}))
    selected = request.get("keep", header)
    if not selected or set(selected) - set(header):
        raise ValueError("Selecciona al menos una variable válida.")
    indices = [header.index(name) for name in selected]
    data = folder / "datos.csv"
    with data.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(selected)
        writer.writerows([[row[i] for i in indices] for row in rows])
    profile = engine.phase1_profile(data, folder, overrides=classes)
    profile.update(source_file=str(source), codebook=codebook,
                   recoding=recoding, collapsing=collapsing, binarizing=binarizing)
    if recuperados:
        profile["metadata_applied"] = recuperados
    # Los tipos declarados por el usuario se conservan junto a los datos para reimportarlos.
    if request.get("classes"):
        try:
            profile["metadata_file"] = str(engine.save_metadata(source, classes))
        except OSError as exc:
            profile["metadata_error"] = f"No se pudieron guardar los metadatos: {exc}"
    write_json(folder / "profile.json", profile)
    return profile


def make_backend(request: dict) -> engine.Backend:
    kind = request["backend"]
    if kind == "none" or kind not in engine.PROVIDERS:
        raise ValueError("Selecciona un backend de IA activo.")
    backend = engine.Backend(kind, request["host"], request["model"],
                             request.get("max_tokens", 64000), 0, 0.2,
                             request.get("timeout", 300))
    backend._no_reasoning_options()
    return backend


def unfence_tables(text: str) -> str:
    return re.sub(r"```(?:markdown|md|text)?[ \t]*\n(.*?)```",
                  lambda match: match[1].strip("\n") if MARKDOWN_TABLE.search(match[1]) else match[0],
                  text, flags=re.S | re.I)


def format_r_output(output: str, ok: bool) -> str:
    if not ok:
        return "```text\n" + output + "\n```"
    output = unfence_tables(output)
    if MARKDOWN_TABLE.search(output):
        return output
    lines = [re.sub(r"([\\`*_{}\[\]()#+.!<>|~-])", r"\\\1", line)
             for line in output.splitlines() if line.strip()]
    return "| Resultado |\n| --- |\n" + "\n".join("| " + line + " |" for line in lines)


def converse(request: dict, folder: Path, backend=None) -> dict:
    backend = backend or make_backend(request)
    rs = engine.find_rscript()
    profile = request.get("profile")
    context = []
    if profile:
        context.append("DICCIONARIO (sin filas):\n" +
                       engine.dictionary_text(profile, exposure="schema"))
    else:
        context.append("No hay datos cargados. No se puede calcular sobre datos locales.")
    enabled = request.get("run_r", False)
    context.append("Ejecución local de R: " + ("habilitada" if enabled else "deshabilitada"))
    if enabled and rs:
        # Sin esta lista el modelo adivina la disponibilidad y aborta análisis que sí podía hacer.
        # La interfaz la envía si ya la conoce: recalcularla cuesta unos dos segundos por turno.
        try:
            diagnostico = {"packages": request["packages"]} if request.get("packages") else engine.diagnose_r()
            hay = [p["package"] for p in diagnostico.get("packages", []) if p["installed"]]
            faltan = [p["package"] for p in diagnostico.get("packages", []) if not p["installed"]]
            if hay or faltan:
                context.append("PAQUETES R INSTALADOS Y DISPONIBLES: " + (", ".join(hay) or "ninguno")
                               + ". No instalados: " + (", ".join(faltan) or "ninguno")
                               + ". Esta lista es la del R que ejecutará tu código: no supongas "
                                 "que falta un paquete que aparece como disponible.")
        except Exception as exc:                                   # noqa: BLE001
            engine.log(f"no se pudo listar los paquetes de R: {exc}")
    for turn in request.get("history", [])[-20:]:
        context.append(f"{turn['role']}: {turn['content']}")
    context.append("USUARIO: " + request["ask"])
    # Solo para consultas escritas a mano: las plantillas ya llevan sus propias reglas.
    for guia in ([] if request.get("plantilla") else guias_necesarias(request["ask"])):
        context.append("USO CORRECTO DEL PAQUETE EN LAS VERSIONES INSTALADAS, "
                       "comprobado contra este mismo R:" + guia)
    # Una consulta a mano también merece sus referencias: la plantilla las lleva dentro.
    if not request.get("plantilla"):
        obras = bibliografia_para(request["ask"])
        if obras:
            context.append("BIBLIOGRAFÍA DE ESTA CONSULTA." + CITAS + " ".join(obras))
    # Las firmas se leen del R del usuario en cada consulta: una actualización de paquete
    # cambia los argumentos y una regla escrita a mano se quedaría obsoleta sin avisar.
    if enabled and rs:
        objetivo = funciones_a_documentar(request["ask"])
        if objetivo:
            # Los paquetes se nombran todos: con la lista recortada no se veía si una
            # biblioteca pedida en la consulta se había comprobado o no.
            paquetes = list(dict.fromkeys(f.split("::")[0] for f in objetivo))
            engine.log(f"PASO: Consultando en R la firma real de {len(objetivo)} funciones de "
                       + ", ".join(paquetes))
            firmas = engine.function_signatures(rs, objetivo, temp_dir=folder)
            if firmas:
                context.append(
                    "FIRMAS REALES DE LAS FUNCIONES EN EL R DE ESTE EQUIPO, leídas con args() "
                    "al empezar esta consulta. Son la verdad sobre las versiones instaladas: "
                    "usa exactamente estos argumentos y no inventes ninguno que no aparezca, "
                    "aunque lo recuerdes de otra versión del paquete.\n" + firmas)
    context.append("FORMATO OBLIGATORIO: " + RESULT_FORMAT)
    scripts = []
    last_ok, last_output = False, ""
    last_syntax_error = None
    r_attempts, syntax_errors, help_rounds = 0, 0, 0
    fence_asked = False
    calculated = []

    def finish(answer):
        answer = unfence_tables(answer)
        if calculated and not MARKDOWN_TABLE.search(answer):
            answer += "\n\n### Resultados calculados\n\n" + "\n\n".join(
                format_r_output(output, True) for _, output in calculated)
        if scripts and not last_ok:
            answer += "\n\n### Último error de R\n\n" + format_r_output(last_output, False)
        if last_syntax_error and last_syntax_error not in answer:
            answer += "\n\nEl último bloque R no se ejecutó por un error de sintaxis.\n\n```text\n" + last_syntax_error + "\n```"
        return {"answer": answer, "scripts": scripts}

    def incomplete(reason):
        parts = [reason, "El análisis no se ha completado; se conservan las salidas obtenidas."]
        for step, output in calculated:
            parts.append(f"### Resultados calculados (paso {step})\n\n" + format_r_output(output, True))
        if not calculated:
            parts.append("No se obtuvieron resultados válidos de R.")
        if last_syntax_error:
            parts.append("### Último error de sintaxis\n\n```text\n" + last_syntax_error + "\n```")
        return finish("\n\n".join(parts))

    # Seis propuestas R, tres consultas de ayuda y una respuesta final sin ejecución.
    for attempt in range(1, 11):
        final_only = r_attempts >= 6
        system = SYSTEM
        if final_only:
            system += ("\nFASE FINAL: se agotó el presupuesto de ejecución. Responde solo con tablas "
                       "e interpretación de las salidas recibidas, sin bloques R ni consultas AYUDA. "
                       "Indica qué se calculó, qué falló y qué no se pudo estimar; no inventes resultados.")
        engine.log(f"PASO: {'Redactando la interpretación final' if final_only else 'Consultando al endpoint'}"
                   + (f" (consulta {attempt})" if attempt > 1 else "")
                   + f"; {sum(len(c) for c in context)} caracteres de contexto")
        inicio = _time.perf_counter()
        response = engine.strip_think(backend.chat(system, "\n\n".join(context)))
        engine.log(f"PASO: Respuesta recibida en {_time.perf_counter() - inicio:.1f} s "
                   f"({len(response)} caracteres); analizando lo que pide")
        if backend.last_truncated:
            return finish(response + "\n\nRespuesta truncada; aumenta Máx. tokens.")
        topics = re.findall(r"^\s*AYUDA:\s*(.+?)\s*$", response, re.M)
        code = engine.extract_r(response)
        if final_only or not response:
            if code or topics or not response:
                return incomplete("La IA no cerró la interpretación con las salidas disponibles.")
            return finish(response)
        if topics and enabled:
            if help_rounds >= 3:
                return incomplete("Se alcanzó el límite de consultas de ayuda de R.")
            help_rounds += 1
            engine.log("PASO: Consultando la ayuda de R sobre " + ", ".join(topics)[:120])
            help_text = engine.chat_r_help(rs, topics, temp_dir=folder)
            context.append("AYUDA R:\n" + (help_text or "Ayuda no disponible."))
            continue
        # Código R sin cerca ```r: extract_r no lo ve, se mostraría como prosa y el análisis
        # quedaría sin ejecutar. Se pide una sola vez, bien marcado.
        if (not code and enabled and profile and rs and not fence_asked
                and engine.unfenced_r(response)):
            fence_asked = True
            engine.log("PASO: La respuesta traía código R sin marcar; pidiéndolo como bloque ejecutable")
            context.extend(["ASISTENTE:\n" + response,
                            "Ese código R no se ha ejecutado porque llegó sin la cerca de apertura "
                            "```r. Reenvía solo ese bloque, completo y autocontenido, dentro de una "
                            "cerca ```r, sin mezclar la interpretación con el código."])
            continue
        if not code or not enabled:
            if last_syntax_error:
                response = "No se ejecutó el último código R: contenía un error de sintaxis.\n\n" + response
            return finish(response)
        if not profile or not rs:
            return {"answer": "No se ejecutó R: carga datos y comprueba que Rscript está instalado.\n\n"
                              + response, "scripts": scripts}
        r_attempts += 1
        script = folder / f"analisis_{attempt}.R"
        script.write_text(engine.chat_r_script(code, profile), encoding="utf-8")
        engine.log(f"PASO: Ejecutando el bloque {r_attempts} de código R")
        inicio = _time.perf_counter()
        try:
            ok, output = engine.chat_run_r(code, profile, rs, timeout=request.get("timeout", 300), temp_dir=folder)
            engine.log(f"PASO: R terminó en {_time.perf_counter() - inicio:.1f} s; "
                       + ("enviando sus resultados para interpretarlos" if ok
                          # Sin el motivo en el registro, un bloque rechazado es indiagnosticable:
                          # la carpeta de la operación se borra al terminar la sesión.
                          else "devolviendo el error para que lo corrija: "
                               + " ".join(output.strip().splitlines()[-3:])[:300]))
        except engine.RSyntaxError as exc:
            syntax_errors += 1
            last_syntax_error = str(exc)
            (folder / f"sintaxis_{attempt}.txt").write_text(last_syntax_error, encoding="utf-8")
            if syntax_errors >= 3:
                return finish("No se ejecutó el último código R: sigue conteniendo un error de sintaxis.\n\n"
                              + "```text\n" + last_syntax_error + "\n```")
            # El analizador no evalúa el código: este diagnóstico no contiene salida de los datos.
            context.extend(["ASISTENTE:\n" + code,
                            "ERROR DE SINTAXIS (detectado sin ejecutar ni leer datos):\n" + last_syntax_error,
                            # Reenviar el mismo bloque enorme agota los tres intentos: el error
                            # siempre aparece en una función anónima larga dentro de otra llamada.
                            "Corrige la sintaxis y devuelve únicamente un bloque R completo, más "
                            "corto y simple que el anterior: deja solo lo que falte por calcular, "
                            "parte las funciones anónimas largas en pasos con nombre y revisa las "
                            "llaves y las comas alrededor de la línea indicada. No se ha ejecutado "
                            "este código y no hay resultados que interpretar."])
            continue
        last_syntax_error = None
        syntax_errors = 0
        scripts.append(str(script))
        last_ok, last_output = ok, output
        if ok:
            calculated.append((attempt, output))
        (folder / f"salida_{attempt}.txt").write_text(output, encoding="utf-8")
        # La salida de un script puede incluir filas: no se envía sin consentimiento.
        if not request.get("share_output", False):
            formatted = format_r_output(output, ok)
            return {"answer": ("Resultado de R" if ok else "La ejecución R falló") +
                    ":\n\n" + formatted + "\n\n"
                    "La salida permanece local. Activa su envío si deseas una interpretación por IA.",
                    "scripts": scripts,
                    "context_answer": "Se ejecutó R; la salida se conservó sólo localmente."}
        context.extend(["ASISTENTE:\n" + code,
                        f"SALIDA R ({'OK' if ok else 'ERROR'}):\n{output}",
                        # Sin esta aclaración el modelo cerraba el turno dejando los diagnósticos
                        # anunciados como pendientes: creía que ya no podía enviar más código.
                        "Si falló, devuelve código corregido. Si la petición pide cálculos que esta "
                        "salida todavía no contiene, devuelve otro bloque R con los que falten, "
                        "siempre dentro de una cerca ```r, porque sin ella no se ejecuta: "
                        f"quedan {6 - r_attempts} ejecuciones disponibles. Interpreta la salida sin "
                        "bloque R solo cuando no quede nada por calcular, y entonces no anuncies "
                        "ninguna prueba como pendiente. No inventes cifras."])
    raise RuntimeError("No se obtuvo respuesta.")


def worker(request_path: Path) -> int:
    folder = request_path.parent
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        action = request["action"]
        if action == "profile":
            result = prepare_data(request, folder)
        elif action == "diagnose":
            result = engine.diagnose_r()
        elif action == "selftest":
            import analisisr_ui as ui
            application = ui.QApplication.instance() or ui.QApplication([])
            window = create_window()
            try:
                application.processEvents()
                result = {"title": window.windowTitle(), "tabs": window.tabs.count(),
                          "templates": window.templates.count() - 1,
                          "guide": (ROOT / "assets" / "guia.html").is_file(),
                          "icon": not window.windowIcon().isNull(),
                          "version": VERSION,
                          "frozen": bool(getattr(sys, "frozen", False)),
                          "r_ready": window.r_ready,
                          "tempdir": tempfile.gettempdir(), "session_folder": str(window.folder),
                          "rscript": engine.find_rscript(),
                          "max_tokens": window.tokens.value(), "timeout": window.timeout.value()}
            finally:
                window.close()
        elif action == "probe":
            result = make_backend(request).probe()
            if result.get("error"):
                raise RuntimeError(result["error"])
        elif action == "chat":
            with engine.RunLock(request["backend"], request["host"]):
                result = converse(request, folder)
        else:
            raise ValueError("Acción desconocida.")
        write_json(folder / "result.json", result)
        return 0
    except (Exception, SystemExit) as exc:
        write_json(folder / "result.json", {"error": str(exc)})
        return 1
    finally:
        write_json(folder / "manifest.json", {
            "schema": "analizar.operation/1",
            "artifacts": {path.name: {"sha256": engine.sha256_file(path)}
                          for path in sorted(folder.iterdir())
                          if path.is_file() and path.name != "manifest.json"},
        })


def create_window():
    import analisisr_ui as ui

    class Window(ui.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("AnalizaR Desktop — Estadística con lenguaje natural")
            self.setWindowIcon(ui.QIcon(str(ROOT / "assets" / "analizar.ico")))
            self.resize(1200, 850)
            self.workspace = SessionWorkspace()
            self.folder = self.workspace.folder
            self.profile = None
            self.history = []
            self.proc = None
            self.closing = False
            self.job = 0
            self.r_ready = False
            self.r_diagnosis = []
            self.tabs = ui.QTabWidget()
            self.setCentralWidget(self.tabs)
            self.build_environment()
            self.build_data()
            self.build_endpoints()
            self.build_chat()
            # Sin R no hay cálculo posible: todo lo demás espera a que se detecte.
            self.r_pages = [self.data_page, self.endpoint_page, self.chat_page]
            self.locked_pages = [self.environment_page, self.data_page, self.endpoint_page]
            file_menu = self.menuBar().addMenu("Archivo")
            self.session_actions = []
            for label, shortcut, handler in (
                    ("Guardar sesión…", "Ctrl+S", self.save_session),
                    ("Abrir sesión…", "Ctrl+O", self.open_session),
                    ("Exportar informe a Word…", "Ctrl+Shift+E", self.export_word)):
                action = file_menu.addAction(label)
                action.setShortcut(ui.QKeySequence(shortcut))
                action.triggered.connect(handler)
                self.session_actions.append(action)
            help_action = ui.QAction("Guía de AnalizaR Desktop", self)
            help_action.setObjectName("help_guide")
            help_action.setShortcut(ui.QKeySequence("F1"))
            help_action.triggered.connect(self.open_help)
            help_menu = self.menuBar().addMenu("Ayuda")
            help_menu.addAction(help_action)
            self.diagnose_action = help_menu.addAction("Diagnóstico de R y paquetes")
            self.diagnose_action.triggered.connect(lambda: self.start("diagnose", {}, self.show_diagnosis))
            about_menu = self.menuBar().addMenu("Acerca de")
            about_action = about_menu.addAction("Acerca de AnalizaR Desktop…", self.show_about)
            about_action.setObjectName("about_app")
            self.load_endpoint()
            self.statusBar().showMessage(f"Sesión local: {self.folder}")
            self.update_r_state()

        def build_environment(self):
            page = ui.QWidget()
            layout = ui.QVBoxLayout(page)
            self.r_state = ui.QLabel()
            self.r_state.setWordWrap(True)
            self.r_state.setTextInteractionFlags(ui.Qt.TextSelectableByMouse)
            layout.addWidget(self.r_state)
            row = ui.QHBoxLayout()
            self.r_home = ui.QLineEdit(engine.configured_r_home())
            self.r_home.setPlaceholderText("Carpeta de R, solo si no se detecta automáticamente "
                                           "(por ejemplo C:/Program Files/R/R-4.6.1)")
            browse = ui.QPushButton("Examinar…")
            browse.clicked.connect(self.browse_r_home)
            detect = ui.QPushButton("Volver a detectar")
            detect.clicked.connect(self.refresh_r)
            self.r_check = ui.QPushButton("Comprobar R y paquetes")
            self.r_check.clicked.connect(lambda: self.start("diagnose", {}, self.show_diagnosis))
            row.addWidget(self.r_home, 1)
            row.addWidget(browse)
            row.addWidget(detect)
            row.addWidget(self.r_check)
            layout.addLayout(row)
            self.r_packages = ui._table(["Paquete", "Estado", "Versión"])
            layout.addWidget(self.r_packages, 1)
            self.r_install = ui.QPlainTextEdit()
            self.r_install.setReadOnly(True)
            self.r_install.setMaximumHeight(110)
            layout.addWidget(self.r_install)
            self.environment_page = page
            self.tabs.addTab(page, "1 · Entorno R")

        def browse_r_home(self):
            folder = ui.QFileDialog.getExistingDirectory(self, "Carpeta de instalación de R",
                                                         self.r_home.text() or "C:/Program Files/R")
            if folder:
                self.r_home.setText(folder)
                self.refresh_r()

        def refresh_r(self):
            """Guarda la ruta indicada y vuelve a detectar R sin cerrar la aplicación."""
            chosen = self.r_home.text().strip()
            if chosen and not engine.rscript_in(chosen):
                ui.QMessageBox.warning(self, "Entorno R",
                                       f"No se encuentra {engine.RSCRIPT_NAME} en la carpeta bin de:\n{chosen}")
                return
            try:
                engine.save_r_home(chosen)
            except OSError as exc:
                ui.QMessageBox.warning(self, "Entorno R", f"No se pudo guardar la ruta: {exc}")
                return
            self.update_r_state()

        def update_r_state(self):
            """Aplica el estado de R: sin Rscript no se habilita ninguna otra pestaña."""
            rscript = engine.find_rscript()
            self.r_ready = bool(rscript)
            for page in self.r_pages:
                page.setEnabled(self.r_ready)
            for index in range(self.tabs.count()):
                self.tabs.setTabEnabled(index, self.tabs.widget(index) is self.environment_page or self.r_ready)
            if self.r_ready:
                self.r_state.setText(
                    f"R detectado.\nRscript: {rscript}\n"
                    "Pulsa «Comprobar R y paquetes» para ver la versión y los paquetes instalados.")
                # Si antes faltaba R, la tabla y el aviso de instalación ya no describen el estado.
                if self.r_packages.rowCount() and self.r_packages.item(0, 1).text() == "R no detectado":
                    self.r_packages.setRowCount(0)
                    self.r_install.clear()
                self.statusBar().showMessage(f"Sesión local: {self.folder}")
                return
            required = [name for name in engine.DIAGNOSTIC_PACKAGES if name != "stats"]
            self.r_state.setText(
                "No se ha detectado R, y AnalizaR Desktop no puede funcionar sin él: todos los "
                "procedimientos estadísticos se calculan en R y no hay alternativa en Python.\n\n"
                "Instala R 4.x desde https://cran.r-project.org y, dentro de R, los paquetes "
                "que figuran abajo. Si ya lo tienes en una ruta poco habitual, indícala aquí "
                "y pulsa «Volver a detectar».")
            self.r_packages.setRowCount(len(required))
            for row, name in enumerate(required):
                for col, text in enumerate((name, "R no detectado", "—")):
                    self.r_packages.setItem(row, col, ui.QTableWidgetItem(text))
            self.r_install.setPlainText(
                "Paquetes requeridos. En una consola de R, fuera de AnalizaR Desktop:\n"
                "install.packages(c(" + ", ".join(json.dumps(name) for name in required) + "))")
            self.statusBar().showMessage("Sin R: instala R y sus paquetes para poder trabajar.")

        def build_data(self):
            page = ui.QWidget()
            layout = ui.QVBoxLayout(page)
            row = ui.QHBoxLayout()
            self.data = ui.QLineEdit()
            self.data.setPlaceholderText("CSV, Excel, SPSS, Stata o SAS")
            browse = ui.QPushButton("Importar…")
            browse.clicked.connect(self.browse)
            self.recent = ui.QPushButton("Abrir reciente")
            self.recent_menu = ui.QMenu(self.recent)
            self.recent.setMenu(self.recent_menu)
            self.recent_menu.aboutToShow.connect(self.refresh_recent)
            self.refresh_recent()
            row.addWidget(self.data, 1)
            row.addWidget(browse)
            row.addWidget(self.recent)
            layout.addLayout(row)
            self.table = ui._table(["Usar / Variable", "Tipo", "Ausentes", "Media", "DE"])
            layout.addWidget(self.table, 1)
            self.recode = ui.QPlainTextEdit()
            self.recode.setPlaceholderText("Recodificación, una regla por línea:\nx2 = invertir 1..5\n"
                                           "grupo = 1,2 -> 1; 3,4 -> 2; resto -> NA")
            self.recode.setMaximumHeight(100)
            layout.addWidget(self.recode)
            self.collapse = ui.QSpinBox()
            self.collapse.setRange(0, 10000)
            self.collapse.setPrefix("Fusionar categorías ordinales con menos de: ")
            self.collapse.setSpecialValueText("Sin fusión de categorías")
            layout.addWidget(self.collapse)
            apply_button = ui.QPushButton("Aplicar tratamiento y selección")
            apply_button.clicked.connect(self.apply_data)
            layout.addWidget(apply_button, 0, ui.Qt.AlignLeft)
            hint = ui.QLabel("Las transformaciones afectan a una copia. Los originales se conservan. "
                            "Aplicar limpia el chat para evitar mezclar resultados de datos diferentes.")
            hint.setWordWrap(True)
            layout.addWidget(hint)
            self.data_page = page
            self.tabs.addTab(page, "2 · Datos")

        def build_endpoints(self):
            page = ui.QWidget()
            form = ui.QFormLayout(page)
            form.setFormAlignment(ui.Qt.AlignTop)
            self.provider = ui.QComboBox()
            for kind, defaults in engine.PROVIDERS.items():
                if kind != "none":
                    self.provider.addItem(defaults["label"], kind)
            self.host = ui.QLineEdit()
            self.model = ui.QLineEdit()
            self.key = ui.QLineEdit()
            self.key.setEchoMode(ui.QLineEdit.Password)
            self.key.setPlaceholderText("Clave nueva; vacío conserva la guardada o usa el entorno")
            self.tokens = ui.QSpinBox()
            self.tokens.setRange(256, 200000)
            self.tokens.setValue(64000)
            self.timeout = ui.QSpinBox()
            self.timeout.setRange(10, 3600)
            self.timeout.setValue(300)
            self.timeout.setSuffix(" s")
            for label, widget in (("Proveedor", self.provider), ("URL base", self.host),
                                  ("Modelo", self.model), ("API key", self.key),
                                  ("Máx. tokens", self.tokens), ("Tiempo por operación", self.timeout)):
                form.addRow(label, widget)
            form.addRow("Razonamiento", ui.QLabel("Desactivado · presupuesto 0 (fijo)"))
            save = ui.QPushButton("Guardar endpoint y clave cifrada")
            save.clicked.connect(self.save_endpoint)
            probe = ui.QPushButton("Probar conexión")
            probe.clicked.connect(lambda: self.start("probe", self.endpoint(), self.show_probe))
            actions = ui.QHBoxLayout()
            actions.addWidget(save)
            actions.addWidget(probe)
            actions.addStretch()
            form.addRow(actions)
            self.probe_result = ui.QPlainTextEdit()
            self.probe_result.setReadOnly(True)
            self.probe_result.setPlaceholderText("Pulsa Probar conexión para comprobar el endpoint y el modelo.")
            self.probe_result.setMinimumHeight(140)
            self.probe_result.setMaximumHeight(220)
            form.addRow("Resultado", self.probe_result)
            note = ui.QLabel("Los perfiles cifrados son propios de AnalizaR Desktop. Selecciona un modelo "
                            "que permita desactivar el razonamiento. Cambiar de endpoint limpia la conversación.")
            note.setWordWrap(True)
            form.addRow(note)
            self.provider.currentIndexChanged.connect(self.load_endpoint)
            self.host.textChanged.connect(self.clear_chat)
            self.model.textChanged.connect(self.clear_chat)
            for field in (self.host, self.model, self.key):
                field.textChanged.connect(self.probe_result.clear)
            self.endpoint_page = page
            self.tabs.addTab(page, "3 · Endpoints IA")

        def build_chat(self):
            page = ui.QWidget()
            layout = ui.QVBoxLayout(page)
            self.chat = ui.QTextBrowser()
            self.chat.setObjectName("ai_response")
            self.txt_chat = self.chat
            self.chat.setOpenExternalLinks(False)
            layout.addWidget(self.chat, 1)
            self.question = ui.PromptEdit()
            self.question.variables_requested.connect(self.insert_variables)
            self.question.setObjectName("ai_prompt")
            self.question.setPlaceholderText("Escribe tu consulta. Usa @ para insertar variables del dataset.")
            self.question.setMaximumHeight(95)
            templates = ui.QHBoxLayout()
            self.templates = ui.QComboBox()
            self.templates.addItem("Seleccionar plantilla…")
            self.templates.addItems(TEMPLATES)
            use_template = ui.QPushButton("Usar plantilla")
            use_template.clicked.connect(self.use_template)
            templates.addWidget(self.templates)
            templates.addWidget(use_template)
            templates.addStretch()
            layout.addLayout(templates)
            layout.addWidget(self.question)
            self.run_r = ui.QCheckBox("Ejecutar el R generado en este equipo")
            self.run_r.setChecked(True)
            self.run_r.setToolTip("El código generado se ejecuta con tus permisos. El filtro de "
                                 "operaciones de AnalizaR Desktop no es un aislamiento de seguridad.")
            self.show_code = ui.QCheckBox("Mostrar código R")
            self.show_code.setToolTip("Añade al final de la respuesta el último script R ejecutado.")
            self.share = ui.QCheckBox("Permitir enviar la salida R al endpoint para interpretarla (puede contener datos)")
            self.share.setChecked(True)
            self.share.setToolTip("Marcada por defecto. Si está activa, las salidas de R se envían "
                                  "al endpoint seleccionado. Desmárcala para mantenerlas locales.")
            execution = ui.QHBoxLayout()
            execution.addWidget(self.run_r)
            execution.addWidget(self.show_code)
            execution.addStretch()
            layout.addLayout(execution)
            layout.addWidget(self.share)
            row = ui.QHBoxLayout()
            self.send = ui.QPushButton("Enviar")
            self.send.clicked.connect(self.send_chat)
            clear = ui.QPushButton("Limpiar conversación")
            clear.clicked.connect(self.clear_chat)
            self.cancel = ui.QPushButton("Cancelar")
            self.cancel.setEnabled(False)
            self.cancel.clicked.connect(lambda: self.proc.kill() if self.proc else None)
            files = ui.QPushButton("Abrir archivos de sesión")
            files.clicked.connect(lambda: ui.QDesktopServices.openUrl(ui.QUrl.fromLocalFile(str(self.folder))))
            self.export_button = ui.QPushButton("Exportar a Word")
            self.export_button.clicked.connect(self.export_word)
            for button in (self.send, clear, self.cancel, files, self.export_button):
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
            self.log = ui.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMaximumHeight(120)
            layout.addWidget(self.log)
            note = ui.QLabel("El endpoint recibe el diccionario sin filas. El texto que escribas y, "
                            "si lo autorizas, las salidas R también se envían. Resultados sin auditoría automática.")
            note.setWordWrap(True)
            layout.addWidget(note)
            ui.QShortcut(ui.QKeySequence("Ctrl+Return"), self.question, self.send_chat)
            self.chat_page = page
            self.tabs.addTab(page, "4 · Chat y R")
            self.clear_chat()

        def insert_variables(self):
            if not self.profile:
                self.question.insertPlainText("@")
                self.statusBar().showMessage("Importa un dataset para seleccionar sus variables con @.")
                return
            cursor = self.question.textCursor()
            popup = ui.QDialog(self.question, ui.Qt.Popup)
            popup.setWindowTitle("Variables del dataset")
            popup.resize(340, 320)
            layout = ui.QVBoxLayout(popup)
            layout.addWidget(ui.QLabel("Selecciona una o varias variables"))
            variables = ui.QListWidget()
            variables.addItems([column["column"] for column in self.profile["columns"]])
            variables.setSelectionMode(ui.QAbstractItemView.MultiSelection)
            layout.addWidget(variables)
            buttons = ui.QDialogButtonBox(ui.QDialogButtonBox.Ok | ui.QDialogButtonBox.Cancel)
            buttons.button(ui.QDialogButtonBox.Ok).setText("Insertar variables")
            buttons.button(ui.QDialogButtonBox.Ok).setEnabled(False)
            variables.itemSelectionChanged.connect(lambda: buttons.button(ui.QDialogButtonBox.Ok).setEnabled(
                bool(variables.selectedItems())))
            buttons.accepted.connect(popup.accept)
            buttons.rejected.connect(popup.reject)
            layout.addWidget(buttons)
            position = self.question.mapToGlobal(self.question.cursorRect().bottomLeft())
            available = self.screen().availableGeometry()
            position.setX(max(available.left(), min(position.x(), available.right() - popup.width())))
            position.setY(max(available.top(), min(position.y(), available.bottom() - popup.height())))
            popup.move(position)
            if popup.exec() == ui.QDialog.Accepted:
                cursor.insertText(", ".join(item.text() for item in variables.selectedItems()))
                self.question.setTextCursor(cursor)
            self.question.setFocus()

        def use_template(self):
            if self.proc or self.templates.currentText() not in TEMPLATES:
                return
            if not self.profile:
                ui.QMessageBox.information(self, "Usar plantilla", "Importa tus datos para seleccionar sus variables.")
                return
            try:
                current = self.data_request()
            except ValueError as exc:
                ui.QMessageBox.information(self, "Usar plantilla", str(exc))
                return
            if current != self.applied_request:
                ui.QMessageBox.information(self, "Usar plantilla", "Aplica el tratamiento y la selección de variables antes de usar una plantilla.")
                return
            name = self.templates.currentText()
            text = TEMPLATES[name]
            # Un campo repetido en el prompt es un solo campo del formulario: sin esto la
            # plantilla de mediación pedía cuatro veces cada variable y solo contaba la última.
            fields = list(dict.fromkeys(re.findall(r"\[([^\]]+)\]", text)))
            columns = [c["column"] for c in self.profile["columns"]]
            # Campos cuyas opciones son pruebas, no columnas: el código entre paréntesis
            # es el valor exacto que espera MVN.
            opciones = {
                "pruebas_multivariantes": ["Mardia (mardia)", "Henze-Zirkler (hz)",
                                           "Henze-Wagner (hw)", "Royston (royston)",
                                           "Doornik-Hansen (doornik_hansen)", "Energía (energy)"],
                "pruebas_univariantes": ["Shapiro-Wilk (SW)", "Shapiro-Francia (SF)",
                                         "Anderson-Darling (AD)", "Cramér-von Mises (CVM)",
                                         "Lilliefors (Lillie)"],
            }
            labels = {"variables": "Variables del análisis", "grupo": "Variable de agrupación",
                      "puntuación": "Variable a comparar", "antes": "Medida antes", "después": "Medida después",
                      "variable_1": "Primera variable", "variable_2": "Segunda variable",
                      "respuesta": "Variable dependiente", "predictores": "Variables predictoras", "ítems": "Ítems de la escala",
                      "filas": "Variable de filas", "columnas": "Variable de columnas",
                      "covariables": "Covariables cuantitativas", "exposición": "Exposición (opcional)",
                      "predictor": "Variable independiente", "mediador": "Variable mediadora",
                      "moderador": "Variable moderadora", "agrupamiento": "Agrupación de nivel superior",
                      "medidas": "Medidas repetidas", "evaluaciones": "Columnas de evaluaciones",
                      "tiempo": "Tiempo hasta el evento", "evento": "Evento (1 = ocurre, 0 = censurado)",
                      "factores": "Variables latentes e indicadores",
                      "pruebas_multivariantes": "Pruebas multivariantes",
                      "pruebas_univariantes": "Pruebas univariantes"}
            dialog = ui.QDialog(self)
            dialog.setWindowTitle("Preparar consulta: " + name)
            dialog.resize(560, 400)
            form = ui.QFormLayout(dialog)
            explanation = ui.QLabel("Elige las variables de tus datos. La consulta se preparará con sus nombres reales.")
            explanation.setWordWrap(True)
            form.addRow(explanation)
            widgets = {}
            for field in fields:
                if field in opciones:
                    widget = ui.QListWidget()
                    widget.setSelectionMode(ui.QAbstractItemView.NoSelection)
                    for texto in opciones[field]:
                        casilla = ui.QListWidgetItem(texto)
                        casilla.setFlags((casilla.flags() | ui.Qt.ItemIsUserCheckable)
                                         & ~ui.Qt.ItemIsSelectable)
                        casilla.setCheckState(ui.Qt.Unchecked)
                        widget.addItem(casilla)
                elif field == "factores":
                    widget = ui.FactorBuilder(columns)
                elif field in ("variables", "predictores", "ítems", "covariables", "medidas", "evaluaciones"):
                    widget = ui.QListWidget()
                    widget.addItems(columns)
                    widget.setSelectionMode(ui.QAbstractItemView.MultiSelection)
                else:
                    widget = ui.QComboBox()
                    widget.addItem("Sin agrupar" if name == "Descriptivos" and field == "grupo" else
                                   "Sin exposición (modelar recuentos)" if field == "exposición" else "Selecciona una variable…")
                    widget.addItems(columns)
                widget.setObjectName(field)
                widgets[field] = widget
                form.addRow(labels[field], widget)
            buttons = ui.QDialogButtonBox(ui.QDialogButtonBox.Ok | ui.QDialogButtonBox.Cancel)
            buttons.button(ui.QDialogButtonBox.Ok).setText("Ejecutar análisis")
            selections = {}

            def accept():
                for field, widget in widgets.items():
                    chosen = ([widget.item(i).text() for i in range(widget.count())
                               if widget.item(i).checkState() == ui.Qt.Checked] if field in opciones
                              else [widget.text()] if isinstance(widget, ui.FactorBuilder) and widget.factors
                              else [] if isinstance(widget, ui.FactorBuilder)
                              else [item.text() for item in widget.selectedItems()] if isinstance(widget, ui.QListWidget)
                              else ([widget.currentText()] if widget.currentIndex() > 0 else []))
                    if not chosen and field == "factores":
                        ui.QMessageBox.information(dialog, "Completar selección",
                                                   "Define al menos una variable latente y pulsa "
                                                   "Añadir variable latente.")
                        return
                    if not chosen and not (name == "Descriptivos" and field == "grupo" or field == "exposición"):
                        ui.QMessageBox.information(dialog, "Completar selección", "Selecciona: " + labels[field])
                        return
                    selections[field] = chosen
                for first, second in (("puntuación", "grupo"), ("antes", "después"),
                                      ("variable_1", "variable_2"), ("filas", "columnas"),
                                      ("predictor", "mediador"), ("predictor", "moderador"),
                                      ("respuesta", "predictor"), ("respuesta", "mediador"),
                                      ("respuesta", "moderador"), ("tiempo", "evento")):
                    if first in selections and second in selections and selections[first] == selections[second]:
                        ui.QMessageBox.information(dialog, "Completar selección", "Elige variables distintas para cada campo.")
                        return
                if ("respuesta" in selections and "predictores" in selections
                        and selections["respuesta"][0] in selections["predictores"]):
                    ui.QMessageBox.information(dialog, "Completar selección", "La variable dependiente no puede ser también predictora.")
                    return
                if "covariables" in selections and any(value in selections["covariables"]
                                                       for value in selections["puntuación"] + selections["grupo"]):
                    ui.QMessageBox.information(dialog, "Completar selección", "Las covariables deben ser distintas de la respuesta y del grupo.")
                    return
                multiples = [f for f in ("variables", "predictores", "ítems", "covariables",
                                         "medidas", "evaluaciones") if f in selections]
                for single in ("grupo", "agrupamiento", "tiempo", "evento", "predictor",
                               "mediador", "moderador", "respuesta", "puntuación"):
                    elegido = selections.get(single) or []
                    if elegido and any(elegido[0] in selections[f] for f in multiples):
                        ui.QMessageBox.information(dialog, "Completar selección",
                                                   labels[single] + " no puede estar también entre las "
                                                   "variables analizadas.")
                        return
                if selections.get("exposición") and selections["exposición"][0] in selections["respuesta"] + selections["predictores"]:
                    ui.QMessageBox.information(dialog, "Completar selección", "La exposición debe ser distinta de la respuesta y de los predictores.")
                    return
                if "ítems" in selections and len(selections["ítems"]) < 2:
                    ui.QMessageBox.information(dialog, "Completar selección", "Selecciona al menos dos ítems.")
                    return
                field, minimum = {"Análisis clúster": ("variables", 2),
                                  "Análisis factorial exploratorio": ("variables", 3),
                                  "Ausentes e imputación múltiple": ("variables", 2),
                                  "ANOVA de medidas repetidas": ("medidas", 2),
                                  "Acuerdo entre evaluaciones": ("evaluaciones", 2),
                                  "Correlación": ("variables", 2),
                                  "Normalidad": ("variables", 2)}.get(name, (None, 0))
                if field and len(selections[field]) < minimum:
                    ui.QMessageBox.information(dialog, "Completar selección",
                                               f"Selecciona al menos {minimum}: " + labels[field])
                    return
                dialog.accept()

            buttons.accepted.connect(accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec() == ui.QDialog.Accepted:
                if name == "Descriptivos" and not selections["grupo"]:
                    text = text.replace(" por [grupo]", "")
                # Un corchete que no sea un campo se deja intacto: antes lanzaba KeyError
                # dentro del slot de Qt y la consulta se quedaba vacía sin explicación.
                text = re.sub(r"\[([^\]]+)\]",
                              lambda m: (", ".join(selections[m[1]]) or "no especificada")
                              if m[1] in selections else m[0], text)
                # El prompt no pasa por el cuadro de consulta: se envía directamente.
                self.send_chat(text.strip(), name)

        def save_session(self):
            if self.proc:
                return
            name, _ = ui.QFileDialog.getSaveFileName(self, "Guardar sesión", "sesion.analizar",
                                                    "Sesión AnalizaR Desktop (*.analizar)")
            if not name:
                return
            try:
                import analisisr_session as sessions
                columns = []
                for row in range(self.table.rowCount()):
                    columns.append({"column": self.table.item(row, 0).text(),
                                    "class": self.table.cellWidget(row, 1).currentText(),
                                    "n_missing": self.table.item(row, 2).text(),
                                    "mean": self.table.item(row, 3).text(), "sd": self.table.item(row, 4).text()})
                state = {"profile": self.profile, "history": self.history,
                         "table_profile": dict(self.profile, columns=columns) if self.profile else None,
                         "data_request": self.data_request() if self.profile else None,
                         "applied_request": getattr(self, "applied_request", None),
                         "endpoint": self.endpoint(), "question": self.question.toPlainText(),
                         "show_code": self.show_code.isChecked(),
                         "job": self.job}
                path = Path(name).with_suffix(".analizar")
                self.workspace.restore()
                sessions.save_session(path, self.folder, state)
                self.statusBar().showMessage(f"Sesión guardada: {path}")
            except Exception as exc:
                ui.QMessageBox.warning(self, "Guardar sesión", str(exc))
            finally:
                self.clean_temporaries()

        def open_session(self):
            if self.proc:
                return
            # .analisisr es la extensión del nombre anterior: se sigue abriendo.
            name, _ = ui.QFileDialog.getOpenFileName(self, "Abrir sesión", "",
                                                     "Sesión AnalizaR Desktop (*.analizar *.analisisr)")
            if not name:
                return
            if (self.history or self.profile or self.question.toPlainText().strip()) and ui.QMessageBox.question(
                    self, "Abrir sesión", "¿Abrir otra sesión? Guarda antes la actual si deseas conservarla.",
                    ui.QMessageBox.Yes | ui.QMessageBox.No, ui.QMessageBox.No) != ui.QMessageBox.Yes:
                return
            candidate = None
            try:
                import analisisr_session as sessions
                candidate = SessionWorkspace()
                folder = candidate.folder
                state = sessions.load_session(Path(name), folder)
                profile = state.get("profile")
                if profile and not Path(profile.get("data_for_r") or profile["file"]).is_file():
                    raise ValueError("La copia de datos de la sesión no está disponible.")
                self.key.clear()
                self.workspace.close()
                self.workspace = candidate
                self.folder = folder
                self.profile = None
                self.table.setRowCount(0)
                self.data.clear()
                self.recode.clear()
                self.collapse.setValue(0)
                if profile:
                    self.loaded(state.get("table_profile") or profile)
                    self.profile = profile
                    treatment = state["data_request"]
                    keep = treatment["keep"]
                    for row in range(self.table.rowCount()):
                        self.table.item(row, 0).setCheckState(
                            ui.Qt.Checked if self.table.item(row, 0).text() in keep else ui.Qt.Unchecked)
                    self.recode.setPlainText(treatment.get("recode", ""))
                    self.collapse.setValue(treatment.get("collapse", 0))
                self.applied_request = state.get("applied_request")
                self.job = int(state.get("job", 0))
                self.history = state.get("history", [])
                self.chat.clear()
                for turn in self.history:
                    ui.render_chat(self.chat, "Tú" if turn["role"] == "user" else "AnalizaR Desktop", turn["content"])
                self.question.setPlainText(state.get("question", ""))
                self.show_code.setChecked(state.get("show_code", False))
                self.statusBar().showMessage("Sesión abierta. Se mantienen el endpoint y las opciones de ejecutar R y enviar su salida.")
            except Exception as exc:
                ui.QMessageBox.warning(self, "Abrir sesión", str(exc))
            finally:
                if candidate is self.workspace:
                    self.clean_temporaries()
                elif candidate is not None:
                    candidate.close()

        def export_word(self):
            if self.proc:
                return
            if not self.history:
                ui.QMessageBox.information(self, "Exportar a Word", "Aún no hay resultados para exportar.")
                return
            name, _ = ui.QFileDialog.getSaveFileName(self, "Exportar informe a Word", "AnalizaR.docx",
                                                    "Documento Word (*.docx)")
            if not name:
                return
            try:
                from analisisr_docx import markdown_to_docx
                parts = []
                for turn in self.history:
                    parts.append("## " + ("Pregunta" if turn["role"] == "user" else "Resultado"))
                    parts.append(turn["content"])
                    if turn.get("scripts") and not turn.get("code_displayed"):
                        try:
                            code = self.workspace.read_text(turn["scripts"][-1])
                            parts.append("### Código R\n\n```r\n" + code + "\n```")
                        except OSError:
                            parts.append("El archivo de código R ya no está disponible en esta sesión.")
                destination = Path(name).with_suffix(".docx")
                if destination.resolve().is_relative_to(self.folder):
                    raise ValueError("Guarda el informe fuera de la carpeta temporal de trabajo.")
                path = markdown_to_docx("\n\n".join(parts), destination,
                                        titulo="Informe de AnalizaR Desktop", pie="Resultados sin auditoría estadística automática.")
                self.statusBar().showMessage(f"Informe Word guardado: {path}")
            except Exception as exc:
                ui.QMessageBox.warning(self, "Exportar a Word", str(exc))



        def show_diagnosis(self, result):
            """Resultado del diagnóstico en la pestaña Entorno R, su único sitio."""
            self.tabs.setCurrentIndex(self.tabs.indexOf(self.environment_page))
            packages = result.get("packages", [])
            self.r_diagnosis = packages          # se reenvía al chat para no recalcularlo
            absent = [item["package"] for item in packages if not item["installed"]]
            # La guía documenta esta misma lista: la comprobación debe decir si está completa.
            verdict = ("Faltan " + str(len(absent)) + " de " + str(len(packages))
                       + " bibliotecas requeridas: " + ", ".join(absent)) if absent else (
                "Todas las bibliotecas requeridas están disponibles ("
                + str(len(packages)) + " comprobadas).")
            self.r_state.setText(result.get("message") or
                                 (f"{result.get('version', '')}\nRscript: {result.get('rscript')}\n"
                                  + "Bibliotecas: " + "; ".join(result.get("libraries", []))
                                  + "\n" + verdict))
            self.r_packages.setRowCount(len(packages))
            for row, item in enumerate(packages):
                for col, text in enumerate((item["package"], "Instalado" if item["installed"] else "Falta instalar",
                                            item["version"] if item["installed"] else "—")):
                    self.r_packages.setItem(row, col, ui.QTableWidgetItem(text))
            self.r_install.setPlainText(
                "Faltan bibliotecas requeridas. En una consola de R, fuera de AnalizaR Desktop:\n"
                "install.packages(c(" + ", ".join(json.dumps(name) for name in absent) + "))"
                if absent else "Todas las bibliotecas comprobadas están instaladas.")

        def show_about(self):
            ui.QMessageBox.about(self, "Acerca de AnalizaR Desktop",
                                f"<h3>AnalizaR Desktop {VERSION}</h3>"
                                "<p>Desarrollado por Eulogio Cordón 2026.</p>")

        def open_help(self):
            path = ROOT / "assets" / "guia.html"
            if not path.is_file():
                ui.QMessageBox.warning(self, "Ayuda", f"No se encuentra el archivo de ayuda:\n{path}")
            elif not ui.QDesktopServices.openUrl(ui.QUrl.fromLocalFile(str(path))):
                ui.QMessageBox.warning(self, "Ayuda", f"No se pudo abrir el navegador. Abre este archivo:\n{path}")

        def clear_chat(self, *_):
            self.history.clear()
            if hasattr(self, "chat"):
                self.chat.setPlainText("Plantea un procedimiento estadístico. Para calcular, carga datos y activa R.")

        def load_endpoint(self, *_):
            kind = self.provider.currentData()
            defaults = engine.provider_defaults(kind)
            saved = secrets.load().get(kind, {})
            self.host.setText(saved.get("host") or defaults.get("host", ""))
            self.model.setText(saved.get("model") or defaults.get("model") or "")
            self.key.clear()
            self.clear_chat()

        def endpoint(self):
            return {"backend": self.provider.currentData(), "host": self.host.text().strip(),
                    "model": self.model.text().strip(), "max_tokens": self.tokens.value(),
                    "timeout": self.timeout.value(), "reasoning_budget": 0}

        def save_endpoint(self):
            try:
                info = self.endpoint()
                make_backend(info)
                secrets.upsert(info["backend"], info["host"], info["model"], self.key.text() or None)
                self.key.clear()
                self.statusBar().showMessage("Endpoint guardado; clave cifrada si se proporcionó.")
            except Exception as exc:
                ui.QMessageBox.warning(self, "No se pudo guardar", str(exc))

        def browse(self):
            name, _ = ui.QFileDialog.getOpenFileName(
                self, "Importar datos", "", "Datos (" + " ".join("*" + ext for ext in engine.INPUT_FORMATS) + ")")
            if name:
                self.open_data(name)

        def refresh_recent(self):
            self.recent_menu.clear()
            paths = recent_data_files()
            for path in paths:
                action = self.recent_menu.addAction(str(path).replace("&", "&&"))
                action.triggered.connect(lambda checked=False, selected=path: self.open_data(selected))
            self.recent.setEnabled(bool(paths))

        def open_data(self, path):
            if self.proc:
                return
            if not Path(path).is_file():
                ui.QMessageBox.warning(self, "Importar datos", f"El archivo ya no está disponible:\n{path}")
                return
            self.start("profile", {"data": str(path)}, self.imported)

        def imported(self, profile):
            self.loaded(profile)
            try:
                remember_data_file(Path(profile["source_file"]))
                self.refresh_recent()
            except OSError as exc:
                self.log.appendPlainText(f"No se pudo actualizar la lista de archivos recientes: {exc}")

        def loaded(self, profile):
            self.profile = profile
            self.data.setText(profile["source_file"])
            self.clear_chat()
            self.recode.clear()
            self.collapse.setValue(0)
            self.table.setRowCount(len(profile["columns"]))
            for row, column in enumerate(profile["columns"]):
                item = ui.QTableWidgetItem(column["column"])
                item.setFlags((item.flags() | ui.Qt.ItemIsUserCheckable) & ~ui.Qt.ItemIsEditable)
                item.setCheckState(ui.Qt.Checked)
                self.table.setItem(row, 0, item)
                combo = ui.QComboBox()
                combo.addItems(list(engine.MEASURE_TYPES))
                combo.setCurrentText(column["class"])
                self.table.setCellWidget(row, 1, combo)
                for index, key in enumerate(("n_missing", "mean", "sd"), 2):
                    value = ui.QTableWidgetItem(str(column.get(key, "")))
                    value.setFlags(value.flags() & ~ui.Qt.ItemIsEditable)
                    self.table.setItem(row, index, value)
            # Solo .get(): una línea de registro no puede abortar la importación.
            recuperados = (profile.get("metadata_applied") or {}).get("applied") or []
            if recuperados:
                cambios = ", ".join(f"{c.get('column')}: {c.get('from')} → {c.get('to')}"
                                    for c in recuperados)
                self.log.appendPlainText("Tipos recuperados del archivo de metadatos: " + cambios)
            for cambio in profile.get("binarizing") or []:
                if cambio.get("recoded"):
                    self.log.appendPlainText(
                        f"Variable binaria {cambio.get('column')} recodificada a 0/1: "
                        f"{cambio.get('reference')}=0 (referencia), {cambio.get('event')}=1")
            if profile.get("metadata_file"):
                self.log.appendPlainText("Tipos guardados en " + profile["metadata_file"])
            if profile.get("metadata_error"):
                self.log.appendPlainText(profile["metadata_error"])
            self.statusBar().showMessage(f"{profile['n_rows']} filas · {profile['n_cols']} variables · {self.folder}")

        def data_request(self):
            if not self.profile or Path(self.data.text()).resolve() != Path(self.profile["source_file"]):
                raise ValueError("Importa el archivo con el botón Importar antes de continuar.")
            keep, classes = [], {}
            for row in range(self.table.rowCount()):
                name = self.table.item(row, 0).text()
                classes[name] = self.table.cellWidget(row, 1).currentText()
                if self.table.item(row, 0).checkState() == ui.Qt.Checked:
                    keep.append(name)
            if not keep:
                raise ValueError("Selecciona al menos una variable.")
            return {"data": self.data.text(), "keep": keep, "classes": classes,
                    "recode": self.recode.toPlainText(), "collapse": self.collapse.value()}

        def apply_data(self):
            try:
                request = self.data_request()
                # Se parte siempre del origen; así una inversión no se aplica dos veces.
                self.start("profile", request, self.applied)
            except ValueError as exc:
                ui.QMessageBox.warning(self, "Datos", str(exc))

        def applied(self, profile):
            # Mantener las reglas permite reconstruir la misma copia en cada consulta.
            self.profile = profile
            self.clear_chat()
            by_name = {col["column"]: col for col in profile["columns"]}
            for row in range(self.table.rowCount()):
                column = by_name.get(self.table.item(row, 0).text())
                if column:
                    for index, key in enumerate(("n_missing", "mean", "sd"), 2):
                        self.table.item(row, index).setText(str(column.get(key, "")))
            self.statusBar().showMessage(f"Tratamiento aplicado: {profile['n_cols']} variables seleccionadas.")

        def send_chat(self, ask=None, plantilla=None):
            # clicked(bool) conecta aquí: solo una cadena cuenta como consulta.
            ask = ask.strip() if isinstance(ask, str) else self.question.toPlainText().strip()
            if self.proc or not ask:
                return
            try:
                fields = {field for text in TEMPLATES.values() for field in re.findall(r"\[([^\]]+)\]", text)}
                columns = {c["column"] for c in self.profile["columns"]} if self.profile else set()
                pending = [field for field in re.findall(r"(?<![\w.])\[([^\[\]\n]+)\]", ask)
                           if field in fields and "[" + field + "]" not in columns]
                if pending:
                    raise ValueError("La consulta conserva campos de una plantilla sin completar: " + ", ".join(pending)
                                     + ". Usa una plantilla para elegir las variables o sustituye esos campos por sus nombres.")
                if self.profile and self.data_request() != self.applied_request:
                    raise ValueError("Aplica el tratamiento y la selección antes de enviar la consulta.")
                request = dict(self.endpoint(), ask=ask,
                               profile=self.profile,
                               history=[{"role": turn["role"],
                                         "content": turn.get("context", turn["content"])}
                                        for turn in self.history],
                               run_r=self.run_r.isChecked(), share_output=self.share.isChecked(),
                               show_code=self.show_code.isChecked(), packages=self.r_diagnosis,
                               plantilla=plantilla or "")
                etiqueta = "Análisis solicitado: " + plantilla if plantilla else request["ask"]
                ui.render_chat(self.chat, "Tú",
                               "Realizando análisis solicitado… Espere por favor."
                               if plantilla else request["ask"])
                self.start("chat", request, lambda result: self.answered(
                    request["ask"], result, request["show_code"], etiqueta))
            except ValueError as exc:
                ui.QMessageBox.warning(self, "Datos pendientes", str(exc))

        def progress(self, line):
            """Todo va al registro; los pasos marcados se anuncian además en el chat."""
            self.log.appendPlainText(line)
            marca = "PASO: "
            if marca in line:
                ui.render_step(self.chat, line.split(marca, 1)[1].strip())

        def answered(self, question, result, show_code=False, display=None):
            answer = result["answer"]
            code_displayed = False
            if show_code and result.get("scripts"):
                try:
                    code = self.workspace.read_text(result["scripts"][-1])
                    answer += "\n\n### Código R\n\n```r\n" + code.rstrip() + "\n```"
                    code_displayed = True
                except OSError as exc:
                    self.log.appendPlainText(f"No se pudo leer el código R: {exc}")
            self.history.extend([{"role": "user", "content": display or question,
                                  "context": question},
                                 {"role": "assistant", "content": answer,
                                  "scripts": result.get("scripts", []), "code_displayed": code_displayed,
                                  "context": result.get("context_answer", result["answer"])}])
            self.chat.clear()
            for turn in self.history:
                ui.render_chat(self.chat, "Tú" if turn["role"] == "user" else "AnalizaR Desktop",
                                          turn["content"])
            self.question.clear()
            for script in result.get("scripts", []):
                self.log.appendPlainText("Script conservado en la sesión: " + Path(script).name)

        def show_probe(self, result):
            error = result.get("error")
            status = "No se pudo conectar" if error else "Conexión correcta"
            kind = result.get("kind") or result.get("backend") or self.provider.currentData()
            lines = [status,
                     f"Proveedor: {engine.provider_defaults(kind)['label']}",
                     f"URL: {result.get('host') or self.host.text()}",
                     f"Modelo configurado: {result.get('model') or self.model.text() or 'Sin especificar'}",
                     f"Modelo informado por el servidor: {result.get('model_alias') or 'No informado'}"]
            lines.append("Razonamiento solicitado: desactivado (presupuesto 0)")
            if error:
                lines.append(f"Error: {error}")
            if result.get("n_ctx") is not None:
                lines.append(f"Ventana de contexto: {result['n_ctx']} tokens")
            if result.get("available_models"):
                lines.append("Modelos disponibles: " + ", ".join(result["available_models"]))
            if result.get("warning"):
                lines.append("Aviso: " + result["warning"])
            self.probe_result.setPlainText("\n".join(lines))
            self.statusBar().showMessage(status + ". Detalles en Endpoints IA.")

        def start(self, action, request, callback):
            if self.proc:
                return
            if action != "diagnose" and not self.r_ready:
                ui.QMessageBox.warning(self, "Entorno R",
                                       "Sin R instalado no se puede ejecutar ninguna operación. "
                                       "Configura el entorno en la pestaña Entorno R.")
                return
            if action == "probe":
                self.probe_result.setPlainText("Comprobando conexión…")
            try:
                self.workspace.restore()
                env = {}
                if action in ("probe", "chat"):
                    token = secrets.load().get(request["backend"], {}).get("api_key", "")
                    key = self.key.text() or (secrets.decrypt(token) if token else "")
                    if key:
                        env["ANALIZAR_API_KEY"] = key
                        provider_env = engine.provider_defaults(request["backend"]).get("key_env")
                        if provider_env:
                            env[provider_env] = key
                self.job += 1
                folder = self.folder / f"operacion_{self.job:03d}"
                folder.mkdir()
                request = dict(request, action=action)
                write_json(folder / "request.json", request)
                self.proc = ui.Proc(self)
                self.proc.line.connect(self.progress)
                self.proc.failed.connect(lambda message: self.finished(folder, -1, callback, request, message))
                self.proc.done.connect(lambda code: self.finished(folder, code, callback, request))
                for page in self.locked_pages:
                    page.setEnabled(False)
                self.send.setEnabled(False)
                self.cancel.setEnabled(True)
                self.question.setEnabled(False)
                for item in self.session_actions + [self.diagnose_action, self.export_button]:
                    item.setEnabled(False)
                self.statusBar().showMessage("Operación en curso…")
                if getattr(sys, "frozen", False):
                    worker_name = "AnalizaRWorker.exe" if sys.platform.startswith("win") else "AnalizaRWorker"
                    program = str(Path(sys.executable).with_name(worker_name))
                    args = ["--worker", str(folder / "request.json")]
                else:
                    program = sys.executable
                    args = [str(Path(__file__).resolve()), "--worker", str(folder / "request.json")]
                self.proc.start(program, args, ROOT, env)
            except Exception as exc:
                if self.proc is not None:
                    self.finished(folder, -1, callback, request, str(exc))
                elif action == "probe":
                    self.show_probe(dict(request, error=str(exc)))
                else:
                    ui.QMessageBox.warning(self, "Operación", str(exc))
                if self.proc is None:
                    self.clean_temporaries()

        def finished(self, folder, code, callback, request, error=""):
            if self.proc is None:
                return
            self.proc.deleteLater()
            self.proc = None
            if self.closing:
                return
            for page in self.locked_pages:
                page.setEnabled(True)
            self.send.setEnabled(True)
            self.cancel.setEnabled(False)
            self.question.setEnabled(True)
            for item in self.session_actions + [self.diagnose_action, self.export_button]:
                item.setEnabled(True)
            self.statusBar().showMessage(f"Sesión: {self.folder}")
            self.update_r_state()
            try:
                path = folder / "result.json"
                result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if code != 0 or "error" in result:
                    raise RuntimeError(result.get("error") or error or "Operación cancelada o interrumpida.")
                callback(result)
                if request["action"] == "profile":
                    self.applied_request = self.data_request()
            except Exception as exc:
                self.log.appendPlainText(str(exc))
                if request["action"] == "probe":
                    self.show_probe(dict(request, error=str(exc)))
                else:
                    ui.QMessageBox.warning(self, "Operación", str(exc))
            finally:
                self.clean_temporaries()
                if not self.folder.exists():
                    self.statusBar().showMessage("Sesión en memoria. Archivos temporales eliminados.")

        def clean_temporaries(self):
            try:
                self.workspace.suspend()
                engine.cleanup_stale_locks()
            except (OSError, ValueError, MemoryError) as exc:
                self.log.appendPlainText(f"No se pudieron limpiar los temporales: {exc}")
                self.statusBar().showMessage("No se pudieron limpiar todos los temporales; consulta el registro.")

        def closeEvent(self, event):
            self.closing = True
            if self.proc and self.proc.running:
                process = self.proc.p
                self.proc.kill()
                process.waitForFinished(3000)
                if self.proc and self.proc.running:
                    self.closing = False
                    ui.QMessageBox.warning(self, "Cerrar", "No se ha detenido el proceso. Vuelve a intentar cerrar.")
                    event.ignore()
                    return
            try:
                self.workspace.close()
                engine.cleanup_stale_locks()
            except (OSError, ValueError) as exc:
                self.closing = False
                ui.QMessageBox.warning(self, "Limpieza de temporales", str(exc))
                event.ignore()
                return
            event.accept()

    return Window()


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        # El registro va por stdout: sin fijar UTF-8 el ejecutable congelado usa la página
        # de códigos del sistema y las tildes llegan al panel como signos raros.
        for flujo in (sys.stdout, sys.stderr):
            try:
                flujo.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError):
                pass
        configure_temporaries(Path(sys.argv[2]).parent)
        return worker(Path(sys.argv[2]))
    configure_temporaries()
    import analisisr_ui as ui

    app = ui.QApplication(sys.argv)
    app.setApplicationName("AnalizaR Desktop")
    app.setWindowIcon(ui.QIcon(str(ROOT / "assets" / "analizar.ico")))
    app.setStyle("Fusion")
    app.setStyleSheet(ui.QSS)
    window = create_window()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
