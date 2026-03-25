from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import swisseph as swe
import itertools
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from datetime import datetime, timedelta
import pytz

app = FastAPI(title="Astrology Chart API")

# Allow the React frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # <-- This wildcard allows a mobile app to connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

PLANETS = {
    swe.SUN: "Sun", swe.MOON: "Moon", swe.MERCURY: "Mercury",
    swe.VENUS: "Venus", swe.MARS: "Mars", swe.JUPITER: "Jupiter",
    swe.SATURN: "Saturn"
}

# Vimshottari Dasa Sequence and Years
DASA_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, 
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}

ASPECTS = [
    {"name": "Conjunction", "angle": 0, "orb": 8},
    {"name": "Sextile", "angle": 60, "orb": 6},
    {"name": "Square", "angle": 90, "orb": 8},
    {"name": "Trine", "angle": 120, "orb": 8},
    {"name": "Opposition", "angle": 180, "orb": 8}
]

# Helper Functions
def get_zodiac_info(longitude):
    sign_index = int(longitude // 30)
    degree = longitude % 30
    return ZODIAC_SIGNS[sign_index], round(degree, 2)

def calculate_aspects(planet_data):
    calculated_aspects = []
    pairs = itertools.combinations(planet_data, 2)
    for p1, p2 in pairs:
        distance = abs(p1["absolute_longitude"] - p2["absolute_longitude"])
        if distance > 180:
            distance = 360 - distance
        for aspect in ASPECTS:
            if abs(distance - aspect["angle"]) <= aspect["orb"]:
                calculated_aspects.append({
                    "planet1": p1["name"],
                    "planet2": p2["name"],
                    "aspect": aspect["name"],
                    "exact_angle": round(distance, 2)
                })
                break
    return calculated_aspects

geolocator = Nominatim(user_agent="starcast_app_render_deployment_123")
tf = TimezoneFinder()

def normalize_birth_data(city_string, local_year, local_month, local_day, local_hour, local_minute):
    location = geolocator.geocode(city_string, timeout=10)
    if not location:
        raise ValueError(f"Could not find coordinates for: {city_string}")
        
    lat, lon = location.latitude, location.longitude
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        raise ValueError("Could not determine the timezone.")
        
    local_tz = pytz.timezone(tz_name)
    
    naive_dt = datetime(local_year, local_month, local_day, local_hour, local_minute, 0)
    localized_dt = local_tz.localize(naive_dt) 
    utc_dt = localized_dt.astimezone(pytz.utc)
    utc_decimal_hour = utc_dt.hour + (utc_dt.minute / 60.0)

    return lat, lon, utc_dt.year, utc_dt.month, utc_dt.day, utc_decimal_hour, tz_name, location.address

# Main API Route
@app.get("/api/chart")
def get_astrology_chart(
    city: str = Query(..., description="Birth city (e.g., 'Paris, France')"),
    year: int = Query(..., description="Local birth year"),
    month: int = Query(..., description="Local birth month"),
    day: int = Query(..., description="Local birth day"),
    hour: int = Query(..., description="Local birth hour"),
    minute: int = Query(..., description="Local birth minute")
):
    try:
        lat, lon, u_yr, u_mo, u_day, u_hr, tz, address = normalize_birth_data(city, year, month, day, hour, minute)
    except ValueError as e:
        import traceback
        traceback.print_exc()  # This forces the terminal to print the red error!
        return {"error": str(e)}
 
    julian_day = swe.julday(u_yr, u_mo, u_day, u_hr)
    
    # Set Lahiri (Chitra Paksha) and combine flags for precision AND SPEED
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    sidereal_flag = swe.FLG_SIDEREAL | swe.FLG_SWIEPH | swe.FLG_SPEED

    planet_results = []
    for planet_id, planet_name in PLANETS.items():
        # Notice we added the sidereal_flag here!
        pos, _ = swe.calc_ut(julian_day, planet_id, sidereal_flag)
        sign, deg = get_zodiac_info(pos[0])
        
        nav_lon = (pos[0] * 9) % 360
        nav_sign, nav_deg = get_zodiac_info(nav_lon)
        
        planet_results.append({
            "name": planet_name, "sign": sign, "degree": deg,
            "absolute_longitude": round(pos[0], 2), "is_retrograde": pos[3] < 0,
            "navamsa_sign": nav_sign, "navamsa_degree": nav_deg
        })

    # Rahu & Ketu
    rahu_pos, _ = swe.calc_ut(julian_day, swe.TRUE_NODE, sidereal_flag)
    rahu_lon = rahu_pos[0]
    r_sign, r_deg = get_zodiac_info(rahu_lon)
    nav_rahu_lon = (rahu_lon * 9) % 360
    nr_sign, nr_deg = get_zodiac_info(nav_rahu_lon)
    
    planet_results.append({
        "name": "Rahu", "sign": r_sign, "degree": r_deg,
        "absolute_longitude": round(rahu_lon, 2), "is_retrograde": rahu_pos[3] < 0,
        "navamsa_sign": nr_sign, "navamsa_degree": nr_deg
    })

    ketu_lon = (rahu_lon + 180) % 360
    k_sign, k_deg = get_zodiac_info(ketu_lon)
    nav_ketu_lon = (ketu_lon * 9) % 360
    nk_sign, nk_deg = get_zodiac_info(nav_ketu_lon)
    
    planet_results.append({
        "name": "Ketu", "sign": k_sign, "degree": k_deg,
        "absolute_longitude": round(ketu_lon, 2), "is_retrograde": rahu_pos[3] < 0,
        "navamsa_sign": nk_sign, "navamsa_degree": nk_deg
    })

    # --- NEW: Calculate Sidereal Houses and Ascendant ---
    # --- NEW: Bulletproof Sidereal Ascendant & Midheaven Calculation ---
    # 1. Get the normal Tropical Ascendant and Midheaven
    cusps, ascmc = swe.houses(julian_day, lat, lon, b'P')
    tropical_asc = ascmc[0]
    tropical_mc = ascmc[1]  # Added the Midheaven back!
    
    # 2. Ask Swiss Ephemeris for the exact Lahiri Ayanamsa on this birth date
    ayanamsa = swe.get_ayanamsa_ut(julian_day)
    
    # 3. Manually subtract the Ayanamsa to get the Sidereal positions
    sidereal_asc = (tropical_asc - ayanamsa) % 360
    sidereal_mc = (tropical_mc - ayanamsa) % 360
    
    # 4. Get the signs and degrees
    asc_sign, asc_deg = get_zodiac_info(sidereal_asc)
    mc_sign, mc_deg = get_zodiac_info(sidereal_mc)  # This fixes the NameError!
    
    # Ascendant Navamsa Math (using the new sidereal_asc)
    nav_asc_lon = (sidereal_asc * 9) % 360
    nav_asc_sign, nav_asc_deg = get_zodiac_info(nav_asc_lon)

    house_results = []
    # Loop from 0 to 11 instead
    for i in range(12):
        h_sign, h_deg = get_zodiac_info(cusps[i])
        # Add 1 to 'i' so the house numbers still show up as 1 through 12 in the JSON
        house_results.append({"house": i + 1, "sign": h_sign, "degree": h_deg})

# --- NEW: Vimshottari Dasa Calculation ---
    # 1. Get the Moon's exact sidereal longitude from our calculated planets
    moon_lon = next(p["absolute_longitude"] for p in planet_results if p["name"] == "Moon")
    
    # 2. Calculate the Nakshatra (each is exactly 13 degrees 20 minutes, or 13.3333 degrees)
    nakshatra_span = 360 / 27
    nakshatra_exact = moon_lon / nakshatra_span
    nakshatra_idx = int(nakshatra_exact)
    
    # 3. Calculate how much of the Nakshatra is remaining
    fraction_left = 1.0 - (nakshatra_exact - nakshatra_idx)
    
    # 4. Find the starting Dasa Lord
    start_lord_idx = nakshatra_idx % 9
    start_lord = DASA_LORDS[start_lord_idx]
    balance_years = fraction_left * DASA_YEARS[start_lord]
    
    # 5. Build the timeline of Maha Dasas (Major Periods)
    birth_date = datetime(year, month, day, hour, minute)
    current_date = birth_date
    dasas = []
    
    for i in range(9):
        current_lord_idx = (start_lord_idx + i) % 9
        lord = DASA_LORDS[current_lord_idx]
        
        # The first period only uses the 'balance' of years remaining. The rest use full years.
        years_to_add = balance_years if i == 0 else DASA_YEARS[lord]
        
        # Calculate the end date for this period (using 365.2425 days per year for leap year accuracy)
        end_date = current_date + timedelta(days=years_to_add * 365.2425)
        
        dasas.append({
            "planet": lord,
            "start_date": current_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "duration_years": round(years_to_add, 2)
        })
        
        current_date = end_date

    return {
        "metadata": {"location": address, "timezone": tz},
        "angles": {
            "ascendant": {
                "sign": asc_sign, "degree": asc_deg,
                "navamsa_sign": nav_asc_sign, "navamsa_degree": nav_asc_deg
            },
            "midheaven": {"sign": mc_sign, "degree": mc_deg}
        },
        "houses": house_results,
        "planets": planet_results,
        "aspects": calculate_aspects(planet_results), 
        "dasas": dasas  # <-- Added the Dasa timeline!
    }