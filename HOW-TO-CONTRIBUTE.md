# Preface

Oncowflow is a little opensource project which provide an AI tools for french surgeon cancer specialist.

If you want to contribute, first join our discord : [Link to our discord](https://discord.gg/C2RPhyn9x8)

And post a short message in ask-to-join channel :)

Step to contribute :

- take an existing issue or create a new one like bug/feature/fix etc
- Clone the project andd create a new pr linked with the issue
- tag with bug/fix/feature the pr
- Admin will review the code

## Rules

- Must use only local app, no public api
- Use as must as possible [langchain](https://www.langchain.com/)
- be carefull about data, this application have for goal to threat patient data, so data must stay in hospital

## Work in local

- First, you need a good video cards like nvidia with at least 12Go vram
- take a look in docker/docker-compose.yml and start service who want to have in docker or install them manually
- install python 3.11.X
- go to application/
- install module with `python -m pip install -r requirements-ui.txt` (use python venv) or use our Dockerfile in docker/dockerfiles*
- start programme with :

**Without ui**

```bash
python3 app.py
```

**With ui**

```bash
python3 streamlit run app-ui.py
```

**All Options availables**

```bash
python3 app.py -e
```

exemples:

```bash
APP_LOGS_LEVEL=DEBUG python3 app.py
```

or use exports

## Models

default model to use/pull (in docker or with [client](https://ollama.com/))

```bash
ollama pull nomic-embed-text
ollama pull mistral-nemo
```
