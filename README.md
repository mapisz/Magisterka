## Multimodalna analiza szeregów czasowych w badaniu popularności gier wideo
> Projekt badawczy do pracy magisterskiej badający zależności pomiędzy aktywnością graczy (Steam), oglądalnością transmisji (Twitch) a dyskusją i sentymentem społeczności (Reddit, Steam Reviews) w 2025 roku.
---

## Główne etapy projektu

1. **Gromadzenie danych (`01_data_collection.ipynb`)** – Selekcja i filtrowanie gier ze Steam, pobieranie danych o oglądalności Twitch oraz postów Reddit.
2. **Analiza sentymentu (`02_sentiment_analysis.ipynb`)** – Klasyfikacja sentymentu recenzji i postów za pomocą leksykonu VADER.
3. **Przygotowanie danych (`03_data_prep_and_exploration.ipynb`)** – Czyszczenie braków, agregacja i stworzenie dziennego panelu danych.
4. **Modelowanie ekonometryczne (`04_time_series_analysis.ipynb`)** – Testy stacjonarności ADF, estymacja modeli VAR oraz testy przyczynowości w sensie Grangera.
