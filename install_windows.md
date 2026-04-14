Download the repository
```
git clone https://gitlab.kit.edu/kit/ifl/forschung/sfb1574/inf/jms_usecase_2.git
```

Install poetry
```
pip install poetry
```

Navigate to the repo's folder
```
cd CPPS_Circular_factory_usecases_JMS
```

Setup  a virtual environment
```
python -m poetry config virtualenvs.in-project true
```

Use poetry to install dependencies 
```
python -m poetry install
```

 Run the interface via streamlit
```
python -m poetry run streamlit run Usecase_FlexConveyor_decentral/src/Visualizer/visualizer_main.py
