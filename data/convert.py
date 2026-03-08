#!/usr/bin/env python3
"""Convert OpenFlights CSV data to indexed JSON for the Where Go U module."""

import csv
import json
import io

DATA_DIR = '.'

def parse_field(val):
    """Strip quotes and handle \\N as None."""
    val = val.strip().strip('"')
    if val == '\\N' or val == '':
        return None
    return val

def process_airports():
    airports = {}
    with open(f'{DATA_DIR}/airports.dat', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 14:
                continue
            iata = parse_field(row[4])
            if not iata or iata == '\\N':
                continue
            try:
                lat = float(row[6])
                lon = float(row[7])
            except (ValueError, IndexError):
                continue
            airports[iata] = {
                'name': parse_field(row[1]),
                'city': parse_field(row[2]),
                'country': parse_field(row[3]),
                'lat': round(lat, 4),
                'lon': round(lon, 4)
            }

    with open(f'{DATA_DIR}/airports-indexed.json', 'w') as f:
        json.dump(airports, f, separators=(',', ':'))

    print(f"Airports: {len(airports)} entries")
    return airports

def process_airlines():
    airlines = {}
    with open(f'{DATA_DIR}/airlines.dat', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 8:
                continue
            iata = parse_field(row[3])
            if not iata or iata == '-':
                continue
            airlines[iata] = {
                'name': parse_field(row[1]),
                'country': parse_field(row[6]),
                'active': parse_field(row[7]) == 'Y'
            }

    with open(f'{DATA_DIR}/airlines-indexed.json', 'w') as f:
        json.dump(airlines, f, separators=(',', ':'))

    print(f"Airlines: {len(airlines)} entries")
    return airlines

def process_routes(airports):
    routes = {}  # indexed by source IATA
    skipped = 0

    with open(f'{DATA_DIR}/routes.dat', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 9:
                continue
            airline = parse_field(row[0])
            src = parse_field(row[2])
            dst = parse_field(row[4])
            codeshare = parse_field(row[6]) == 'Y'
            stops = int(row[7]) if row[7].isdigit() else 0
            equipment = parse_field(row[8])

            if not src or not dst:
                skipped += 1
                continue

            # Only include routes where both airports exist in our airport data
            if src not in airports or dst not in airports:
                skipped += 1
                continue

            if src not in routes:
                routes[src] = []

            routes[src].append({
                'dst': dst,
                'al': airline,
                'cs': codeshare,
                'st': stops,
                'eq': equipment
            })

    # Sort each airport's routes by destination
    for src in routes:
        routes[src].sort(key=lambda r: r['dst'])

    with open(f'{DATA_DIR}/routes-indexed.json', 'w') as f:
        json.dump(routes, f, separators=(',', ':'))

    total_routes = sum(len(v) for v in routes.values())
    print(f"Routes: {total_routes} entries across {len(routes)} source airports (skipped {skipped})")
    return routes

if __name__ == '__main__':
    airports = process_airports()
    airlines = process_airlines()
    routes = process_routes(airports)

    # Print file sizes
    import os
    for f in ['airports-indexed.json', 'airlines-indexed.json', 'routes-indexed.json']:
        size = os.path.getsize(f'{DATA_DIR}/{f}')
        print(f"  {f}: {size / 1024:.0f} KB")
