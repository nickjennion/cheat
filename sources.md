# Data Sources & Attribution

## Global Flights — flights.nothanks.net.au

| Module | Source | URL | Usage |
|--------|--------|-----|-------|
| **Where Go U** | OpenSkies.org | https://openskies.org | Original design inspiration and UI concept (screenshot reference) |
| **Where Go U** | airportinformation.com | https://www.airportinformation.com | Scraped for current nonstop route data (1,264 airports, 22,535 routes) |
| **Where Go U** | OpenFlights | https://openflights.org | Static route database from 2014 (66,934 routes), airport lat/lon data, airline database |
| **Where Go U** | OpenSky Network | https://opensky-network.org | Observed flight departures via REST API (OAuth2), route data from ADS-B traffic |
| **Where Go U** | OpenFlights (GitHub) | https://github.com/jpatokal/openflights | Raw .dat files for airports, airlines, and routes |
| **Where Go U** | Leaflet / CartoDB | https://leafletjs.com / https://carto.com | Interactive map rendering with dark tile layer |
| **Where Go U** | Google Flights | https://www.google.com/travel/flights | Deep-link flight search from map popups |
| **Where Go U** | Skyscanner | https://www.skyscanner.com.au | Deep-link flight search from map popups |
| **Where Go U** | Kayak | https://www.kayak.com.au | Deep-link flight search from map popups |
| **Where Go U** | Trip.com | https://au.trip.com | Deep-link flight search from map popups |
| **Where Go U** | Qunar | https://flight.qunar.com | Deep-link flight search from map popups |
| **Where Go U** | Flight Centre | https://www.flightcentre.com.au | Deep-link flight search from map popups |
| **Flights (Western)** | SerpAPI | https://serpapi.com | Google Flights search proxy — flight prices, times, emissions |
| **Flights (Western)** | Google Flights | https://www.google.com/travel/flights | Booking links generated from search results |
| **Flights (Amadeus)** | Amadeus for Developers | https://developers.amadeus.com | Flight offer search via test API (OAuth2, server-side proxy) |
| **All modules** | Kaggle | https://www.kaggle.com | Airport dataset (6,072 airports) used for search autocomplete |
| **All modules** | Vue.js 3 | https://vuejs.org | Frontend framework (CDN) |
| **Navbar** | — | — | Homer Simpson on a plane (logo.png) |
| **Airline logos** | GitHub (Various) | — | Airline logo PNGs by IATA code, synced weekly via cron |

## AI Attribution
| Tool | Usage |
|------|-------|
| Claude (Anthropic) | Built all code, scrapers, region classification, frontend, and infrastructure |
| Gemini (Google) | Provided flight search deep-link URL formats for multiple providers |
