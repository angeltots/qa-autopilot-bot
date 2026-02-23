✈️ QA Autopilot: Discord Bot Multimodal para ClickUp, Jira y Gemini
QA Autopilot es un bot interactivo para Discord que actúa como un puente inteligente (inspirado en el concepto de Model Context Protocol) entre tus herramientas de gestión de proyectos (ClickUp / Jira) y Google Gemini. Su objetivo es automatizar la generación y redacción de Casos de Prueba (Test Cases) a partir de Historias de Usuario, analizando tanto texto como imágenes adjuntas.

🧑‍✈️ La Analogía: El Piloto Automático
Como piloto comercial, sé que el piloto automático no vuela el avión solo. El piloto sigue al mando: monitorea los sistemas, gestiona el plan de vuelo y toma las decisiones críticas. El piloto automático se encarga del trabajo pesado y repetitivo, permitiendo al piloto enfocarse en lo estratégico.

Este proyecto aplica el mismo principio al Quality Assurance.

🎯 ¿Cuál es el Problema?
La creación manual de casos de prueba es una de las tareas más necesarias pero tediosas del ciclo de vida del software. Consume un tiempo valioso que los analistas de QA podrían dedicar a pruebas exploratorias, estrategias de automatización o análisis de riesgos complejos.

💡 La Solución
Esta herramienta no busca reemplazar al analista de QA, sino darle "superpoderes". A través de Discord, el bot:

1. Lee el Contexto: Recibe un ID de tarea (ClickUp o Jira) y extrae título, descripción, comentarios y descarga las imágenes/diagramas adjuntos.

2. Consulta a la IA: Envía todo el contexto (multimodal) a Google Gemini exigiendo validaciones estrictas ("Validate that...").

3. Interactúa contigo: Te muestra un menú desplegable en Discord para que elijas en qué carpeta/lista guardar los tests.

4. Crea y Vincula: Genera los Test Cases en tu plataforma (con el Task Type correcto) y los enlaza a la historia original.

5. Reporta: Te devuelve en Discord una lista limpia, paginada y con links directos a los tests creados.

🛠️ Tech Stack
- Backend & CLI: Python 3.10+, discord.py (para la interfaz de Discord).

- Inteligencia Artificial: Soporte híbrido para Google AI Studio (google-generativeai) o Google Cloud Vertex AI. Soporte Multimodal (Gemini 1.5 Flash/Pro).

- Integraciones API: ClickUp API v2, Jira REST API.

- Configuración: python-dotenv para manejo seguro de credenciales.

🚀 Puesta en Marcha (Getting Started)
Sigue estos pasos para configurar y ejecutar el bot en tu máquina local o servidor.

1. Prerrequisitos
- Python 3.10 o superior.

- Un Token de Bot de Discord (creado desde el Discord Developer Portal).

- Una API Key de ClickUp y/o Jira.

- Una API Key de Google Gemini (Google AI Studio) o credenciales de Google Cloud (Vertex AI).

2. Instalación
Clona este repositorio:

git clone https://github.com/angeltots/qa-autopilot-bot.git
cd mcp-xray-python

Crea y activa un entorno virtual:

# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
Instala las dependencias:

pip install -r requirements.txt

3. Configuración de Credenciales (.env)

🎮 Uso del Bot
Una vez que tu entorno virtual esté activado y tu .env configurado, arranca el bot desde tu terminal:

python src/discord_bot.py
Verás en la consola: 🚀 Bot Paginado Listo: [NombreDeTuBot]

Comandos en Discord
Ve a cualquier canal de tu servidor de Discord donde el bot esté invitado y usa:

Para ClickUp:

!clickup <ID_DE_LA_TAREA>
# Ejemplo: !clickup 86b821fdh
El bot analizará la tarea y te mostrará un menú desplegable para elegir la lista de destino.

Para Jira:
!jira <ISSUE_KEY>
# Ejemplo: !jira PROJ-123

Herramientas de Debug:
!debug_types
# El bot escaneará tu ClickUp y te dirá qué ID corresponde a "Test Case" para ponerlo en tu .env.

🧪 Pruebas Unitarias
El proyecto incluye un conjunto de pruebas unitarias (pytest) para asegurar la calidad de los módulos de generación (Gherkin/LLM) y conectores API.
pytest

🤝 Contribuciones
¡Las contribuciones son bienvenidas! Si tienes ideas para mejorar la herramienta, optimizar los prompts o añadir nuevas integraciones:

1. Haz un Fork del proyecto.

2. Crea tu rama (git checkout -b feature/MejoraIncreible).

3. Haz commit de tus cambios (git commit -m 'Añade MejoraIncreible').

4. Haz push a la rama (git push origin feature/MejoraIncreible).

5. Abre un Pull Request.

📄 Licencia
Este proyecto está bajo la Licencia MIT. Consulta el archivo LICENSE para más detalles.
