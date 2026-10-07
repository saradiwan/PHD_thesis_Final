# app.py (Full — AHP + India-only map + mobile-safe popup + dynamic colored progress bar)
# -------------------------------------------------------------
import math
from typing import Dict
import numpy as np
import streamlit as st
import requests

# Folium map
try:
    import folium
    from streamlit_folium import st_folium
    from folium import plugins, IFrame
except Exception:
    folium = None
    st_folium = None

# Geopy for English place names
try:
    from geopy.geocoders import Nominatim
except Exception:
    Nominatim = None

st.set_page_config(
    page_title="Real-Time AHP Site Suitability",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------
# Utilities
# ------------------------------
EARTH_R = 6371.0088  # km

def haversine_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * EARTH_R * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ------------------------------
# NASA POWER API
# ------------------------------
@st.cache_data(show_spinner=False)
def fetch_solar_radiation(lat, lon):
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        'latitude': lat,
        'longitude': lon,
        'community': 'RE',
        'parameters': 'ALLSKY_SFC_SW_DWN',
        'format': 'JSON'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        daily_values = list(
            data['properties']['parameter']['ALLSKY_SFC_SW_DWN'].values()
        )

        avg_value = np.mean(daily_values)

        return np.clip(avg_value / 1000, 0, 1)

    except Exception:
        return 0.5

# ------------------------------
# Reverse Geocode (English)
# ------------------------------
@st.cache_data(show_spinner=False)
def reverse_geocode(lat, lon):
    if Nominatim is None:
        return "Unknown Place"

    try:
        geolocator = Nominatim(
            user_agent="ahp_app",
            timeout=10
        )

        location = geolocator.reverse(
            (lat, lon),
            language="en"
        )

        return location.address if location else "Unknown Place"

    except Exception:
        return "Unknown Place"

# ------------------------------
# AHP Model (unchanged logic)
# ------------------------------
class AHPModel:

    def __init__(self):

        self.criteria = [
            'Technical',
            'Environmental',
            'Social'
        ]

        self.sub_criteria = {

            'Technical': [
                'Solar Radiation',
                'Slope',
                'Proximity to Grid',
                'Land Cost'
            ],

            'Environmental': [
                'Land Use',
                'Distance from Protected Areas',
                'Water Body Buffer'
            ],

            'Social': [
                'Distance from Roads',
                'Proximity to Demand Centers',
                'Population Density'
            ]
        }

        self.main_weights = {
            'Technical': 0.693,
            'Environmental': 0.187,
            'Social': 0.080
        }

        self.sub_weights_local = {

            'Technical': {
                'Solar Radiation': 0.558,
                'Slope': 0.262,
                'Proximity to Grid': 0.130,
                'Land Cost': 0.050
            },

            'Environmental': {
                'Land Use': 0.258,
                'Distance from Protected Areas': 0.637,
                'Water Body Buffer': 0.105
            },

            'Social': {
                'Distance from Roads': 0.637,
                'Proximity to Demand Centers': 0.258,
                'Population Density': 0.105
            }
        }

        self.sub_weights_global = self._compute_global()

    def _compute_global(self):

        g = {}

        for crit in self.criteria:

            g[crit] = {
                sub: self.main_weights[crit] * w
                for sub, w in self.sub_weights_local[crit].items()
            }

        return g

    def set_main_weight(self, crit: str, value: float):

        self.main_weights[crit] = value

        self.sub_weights_global = self._compute_global()

    def score(self, site_values: Dict[str, float]) -> float:

        total = 0.0

        for crit in self.criteria:

            for sub in self.sub_criteria[crit]:

                v = float(
                    site_values.get(sub, 0)
                )

                total += (
                    v *
                    self.sub_weights_global[crit][sub]
                )

        max_sum = sum(
            self.sub_weights_global[crit][sub]
            for crit in self.criteria
            for sub in self.sub_criteria[crit]
        )

        return total / max_sum if max_sum else 0.0

# ------------------------------
# Helpers
# ------------------------------
def score_to_text(score: float) -> str:

    if score >= 0.8:
        return "Highly Suitable"

    if score >= 0.6:
        return "Moderately Suitable"

    if score >= 0.4:
        return "<b>Marginally Suitable</b>"

    return "Not Suitable"


def clamp_lat(lat: float) -> float:
    return min(max(lat, 6.0), 37.0)


def clamp_lon(lon: float) -> float:
    return min(max(lon, 68.0), 97.0)

# ------------------------------
# Site Values (unchanged)
# ------------------------------
def get_site_values(lat, lon):

    solar = fetch_solar_radiation(
        lat,
        lon
    )

    return {

        'Solar Radiation': solar,

        'Slope': np.clip(
            1 - abs(lat-22)/30,
            0,
            1
        ),

        'Proximity to Grid': np.clip(
            1 - abs(lon-75)/20,
            0,
            1
        ),

        'Land Cost': np.clip(
            0.5 + 0.5*np.cos(lon/10),
            0,
            1
        ),

        'Land Use': np.clip(
            0.6 + 0.4*np.sin(lat*lon/1000),
            0,
            1
        ),

        'Distance from Protected Areas': np.clip(
            0.7 - 0.7*np.sin(lat/15),
            0,
            1
        ),

        'Water Body Buffer': np.clip(
            0.5 + 0.5*np.cos(lat/12),
            0,
            1
        ),

        'Distance from Roads': np.clip(
            1 - abs(lat-23)/20,
            0,
            1
        ),

        'Proximity to Demand Centers': np.clip(
            0.5 + 0.5*np.sin(lon/10),
            0,
            1
        ),

        'Population Density': np.clip(
            0.6 + 0.4*np.cos(lat*lon/500),
            0,
            1
        )
    }

# ------------------------------
# UI header & description
# ------------------------------
st.title(
    "🌍 India Solar Site Suitability (AHP)"
)

st.markdown(
    "<div style='color:black; font-size:16px;'>"
    "Discover the best locations in India for solar projects using AHP-based site suitability analysis. "
    "Move the red pin on the map, click anywhere, or type coordinates manually — all results update instantly."
    "</div>",
    unsafe_allow_html=True
)

# ------------------------------
# Sidebar weights
# ------------------------------
ahp = AHPModel()

with st.sidebar:

    st.header("⚖️ Adjust AHP Weights")

    wT = st.slider(
        "Technical",
        0.0,
        1.0,
        ahp.main_weights['Technical'],
        0.01
    )

    wE = st.slider(
        "Environmental",
        0.0,
        1.0,
        ahp.main_weights['Environmental'],
        0.01
    )

    wS = st.slider(
        "Social",
        0.0,
        1.0,
        ahp.main_weights['Social'],
        0.01
    )

    total_main = wT + wE + wS

    if total_main == 0:
        total_main = 1.0

    ahp.set_main_weight(
        'Technical',
        wT / total_main
    )

    ahp.set_main_weight(
        'Environmental',
        wE / total_main
    )

    ahp.set_main_weight(
        'Social',
        wS / total_main
    )

# ------------------------------
# Session state defaults
# ------------------------------
if "lat" not in st.session_state:
    st.session_state["lat"] = 22.7196

if "lon" not in st.session_state:
    st.session_state["lon"] = 75.8577

st.session_state["lat"] = clamp_lat(
    float(st.session_state["lat"])
)

st.session_state["lon"] = clamp_lon(
    float(st.session_state["lon"])
)

# ------------------------------
# IMPORTANT:
# Synchronize manual coordinate
# changes BEFORE creating map
# ------------------------------

if "lat_field_ui" in st.session_state:

    manual_lat = st.session_state["lat_field_ui"]

    if manual_lat is not None:

        manual_lat = clamp_lat(
            float(manual_lat)
        )

        if abs(
            manual_lat -
            st.session_state["lat"]
        ) > 1e-7:

            st.session_state["lat"] = manual_lat


if "lon_field_ui" in st.session_state:

    manual_lon = st.session_state["lon_field_ui"]

    if manual_lon is not None:

        manual_lon = clamp_lon(
            float(manual_lon)
        )

        if abs(
            manual_lon -
            st.session_state["lon"]
        ) > 1e-7:

            st.session_state["lon"] = manual_lon

# ------------------------------
# 1️⃣ Interactive Map Explorer
# ------------------------------
st.subheader(
    "1️⃣ Interactive Map Explorer"
)

st.markdown(
    "<div style='color:black; font-size:14px;'>"
    "Drag the red pin across India to instantly see solar suitability. "
    "Mobile-friendly popups provide scores, recommendations, and location info in real-time."
    "</div>",
    unsafe_allow_html=True
)

st.caption(
    "📌 Red pin draggable; popup updates automatically."
)

if folium and st_folium:

    site_values_now = get_site_values(
        st.session_state["lat"],
        st.session_state["lon"]
    )

    score_now = ahp.score(
        site_values_now
    )

    rec_text_now = score_to_text(
        score_now
    )

    place_name_now = reverse_geocode(
        st.session_state["lat"],
        st.session_state["lon"]
    )

    popup_html = f"""
    <div style="
        font-family: 'Segoe UI',sans-serif;
        font-size:14px;
        padding:10px;
        border-radius:10px;
        border:1px solid #ddd;
        background:#fff;
        max-width:90vw;
        box-sizing:border-box;
    ">

      <div style="
          margin-bottom:6px;
          font-weight:600;
      ">
        📍 {place_name_now}
      </div>

      <div style="
          font-size:13px;
          color:#333;
          margin-bottom:6px;
      ">
        <b>Lat:</b>
        {st.session_state['lat']:.4f}
        &nbsp;

        <b>Lon:</b>
        {st.session_state['lon']:.4f}
      </div>

      <div style="
          font-size:13px;
          margin-bottom:4px;
      ">
        <b>⭐ Score:</b>

        <span style="
            font-weight:700;
            color:black;
        ">
            {score_now:.3f}
        </span>
      </div>

      <div style="
          font-size:13px;
      ">
        <b>✅ Recommendation:</b>

        <span style="
            font-weight:700;
            color:black;
        ">
            {rec_text_now}
        </span>
      </div>

    </div>
    """

    iframe = IFrame(
        html=popup_html,
        width=260,
        height=150
    )

    popup = folium.Popup(
        iframe,
        max_width="100%"
    )

    m = folium.Map(
        location=[
            st.session_state["lat"],
            st.session_state["lon"]
        ],
        zoom_start=6,
        tiles="OpenStreetMap",
        control_scale=True
    )

    plugins.Fullscreen().add_to(m)

    plugins.MousePosition().add_to(m)

    marker = folium.Marker(
        location=[
            st.session_state["lat"],
            st.session_state["lon"]
        ],
        popup=popup,
        draggable=True,
        icon=folium.Icon(
            color="red",
            icon="info-sign"
        )
    )

    marker.add_to(m)

    m.fit_bounds([
        [6, 68],
        [37, 97]
    ])

    # ------------------------------
    # Map interaction
    # ------------------------------
    st_map_data = st_folium(
        m,
        width="100%",
        height=600,
        returned_objects=[
            "last_object_clicked",
            "last_object_dragged",
            "last_clicked"
        ]
    )

    if st_map_data:

        drag_event = (
            st_map_data.get(
                "last_object_dragged"
            )
            or
            st_map_data.get(
                "last_object_clicked"
            )
            or
            st_map_data.get(
                "last_clicked"
            )
        )

        if isinstance(
            drag_event,
            dict
        ):

            lat_new = drag_event.get(
                "lat"
            )

            if lat_new is None:
                lat_new = drag_event.get(
                    "latitude"
                )

            if lat_new is None:
                lat_new = drag_event.get(
                    "y"
                )

            lon_new = drag_event.get(
                "lng"
            )

            if lon_new is None:
                lon_new = drag_event.get(
                    "longitude"
                )

            if lon_new is None:
                lon_new = drag_event.get(
                    "x"
                )

            if (
                lat_new is not None
                and
                lon_new is not None
            ):

                new_lat = clamp_lat(
                    float(lat_new)
                )

                new_lon = clamp_lon(
                    float(lon_new)
                )

                # Only update if location changed
                if (
                    abs(
                        new_lat -
                        st.session_state["lat"]
                    ) > 1e-7
                    or
                    abs(
                        new_lon -
                        st.session_state["lon"]
                    ) > 1e-7
                ):

                    st.session_state["lat"] = new_lat

                    st.session_state["lon"] = new_lon

                    # Keep manual input boxes
                    # synchronized with pin
                    st.session_state[
                        "lat_field_ui"
                    ] = new_lat

                    st.session_state[
                        "lon_field_ui"
                    ] = new_lon

                    # Immediately rebuild everything
                    st.rerun()

# ------------------------------
# 2️⃣ Manual Location Input Hub
# ------------------------------
st.subheader(
    "2️⃣ Manual Location Input Hub"
)

st.markdown(
    "<div style='color:black; font-size:14px;'>"
    "Prefer typing coordinates? Enter latitude & longitude manually. "
    "Input validation ensures coordinates stay within India's bounds and updates the map instantly."
    "</div>",
    unsafe_allow_html=True
)

default_lat = clamp_lat(
    float(st.session_state["lat"])
)

default_lon = clamp_lon(
    float(st.session_state["lon"])
)

lat_input = st.number_input(
    "Latitude (6–37)",
    min_value=6.0,
    max_value=37.0,
    value=default_lat,
    step=0.0001,
    key="lat_field_ui"
)

lon_input = st.number_input(
    "Longitude (68–97)",
    min_value=68.0,
    max_value=97.0,
    value=default_lon,
    step=0.0001,
    key="lon_field_ui"
)

if not (
    6.0 <= lat_input <= 37.0
):

    st.error(
        "❌ Invalid Latitude — please enter a value between 6 and 37."
    )

elif not (
    68.0 <= lon_input <= 97.0
):

    st.error(
        "❌ Invalid Longitude — please enter a value between 68 and 97."
    )

# ------------------------------
# 3️⃣ Criteria Insight Panel
# ------------------------------
st.subheader(
    "3️⃣ Criteria Insight Panel"
)

st.markdown(
    "<div style='color:black; font-size:14px;'>"
    "View normalized values (0–1) for each site parameter. "
    "Higher values indicate better suitability. Colors highlight strong vs weak criteria."
    "</div>",
    unsafe_allow_html=True
)

st.caption(
    "🔍 Green = Good, Red = Needs Attention"
)

site_values = get_site_values(
    st.session_state["lat"],
    st.session_state["lon"]
)

score = ahp.score(
    site_values
)

rec_text = score_to_text(
    score
)

cols = st.columns(2)

for i, (k, v) in enumerate(
    site_values.items()
):

    color_val = (
        "red"
        if v < 0.5
        else
        "green"
    )

    with cols[i % 2]:

        st.markdown(
            f"<span style='color:{color_val}; "
            f"font-weight:bold'>"
            f"{k}: {v:.2f}"
            f"</span>",
            unsafe_allow_html=True
        )

# ------------------------------
# 4️⃣ Suitability Dashboard
# ------------------------------
st.subheader(
    "4️⃣ Suitability Dashboard"
)

st.markdown(
    "<div style='color:black; font-size:14px;'>"
    "AHP-based combined score, percentage, and recommendation are displayed here. "
    "The colored progress bar reflects suitability level at a glance."
    "</div>",
    unsafe_allow_html=True
)

st.markdown(
    f"<div style='font-size:22px; "
    f"font-weight:bold; color:black;'>"
    f"Score: {score:.3f}"
    f"</div>",
    unsafe_allow_html=True
)

score_percentage = int(
    score * 100
)

if score_percentage < 40:

    bar_color = "#e15759"

elif score_percentage < 70:

    bar_color = "#ffb347"

else:

    bar_color = "#2ca02c"

progress_html = f"""
<div style="
    position:relative;
    height:34px;
    background:#f0f0f0;
    border-radius:10px;
    overflow:hidden;
    box-shadow:0 1px 3px rgba(0,0,0,0.08);
">

  <div style="
      width:{score_percentage}%;
      background:{bar_color};
      height:100%;
      transition:width 0.4s ease;
  "></div>

  <div style="
      position:absolute;
      top:0;
      left:50%;
      transform:translateX(-50%);
      height:100%;
      display:flex;
      align-items:center;
      justify-content:center;
      font-weight:800;
      color:#000;
      font-size:16px;
  ">
    {score_percentage}%
  </div>

</div>
"""

st.markdown(
    progress_html,
    unsafe_allow_html=True
)

st.markdown(
    f"<div style='padding:12px; "
    f"background:#fafafa; "
    f"border-radius:10px; "
    f"border:1px solid #eee; "
    f"font-size:16px; "
    f"margin-top:8px;'>"
    f"<b>Recommendation:</b> "
    f"<span style='color:black; "
    f"font-weight:bold;'>"
    f"{rec_text}"
    f"</span></div>",
    unsafe_allow_html=True
)
