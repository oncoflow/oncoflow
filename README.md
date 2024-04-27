# RCP Data generator

## Usage

create venv :

```
python3 -m venv ./venv
. ./venv/bin/activate 
pip install -r requirements.txt
```

```
python3 generate_rcp.py
```

Static parameters:

```
NB_FILES # Nb file to generate
PDF_SRC # pdf source
PDF_DEST # name of pdf file without index
```

## Data model

data model follow models/rcp_data.yaml to generate content, you can modify it to generate other datas