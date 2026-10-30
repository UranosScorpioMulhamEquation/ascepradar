from datetime import datetime, date, time, timedelta
import os
from typing import Dict, List, Tuple, Any, Optional

import geonamescache
import pandas as pd
import pytz
import streamlit as st
import swisseph as swe
from timezonefinder import TimezoneFinder

# ==========================================
# 0. تهيئة مسار ملفات الـ Ephemeris والإعدادات
# ==========================================
EPHE_PATH = "./ephe"
if not os.path.exists(EPHE_PATH):
    os.makedirs(EPHE_PATH)

swe.set_ephe_path(EPHE_PATH)

# ==========================================
# 1. خدمات البيانات الجغرافية والزمنية المتقدمة
# ==========================================
@st.cache_data
def load_geo_data() -> Tuple[geonamescache.GeonamesCache, Dict[str, str], List[str], Dict[str, List[Dict[str, Any]]]]:
    gc = geonamescache.GeonamesCache()
    countries = gc.get_countries()
    cities = gc.get_cities()

    country_map = {c["name"]: code for code, c in countries.items()}
    sorted_countries = sorted(list(country_map.keys()))

    cities_by_country: Dict[str, List[Dict[str, Any]]] = {}
    for c_code in country_map.values():
        c_cities = [city for city in cities.values() if city["countrycode"] == c_code]
        c_cities_sorted = sorted(c_cities, key=lambda x: x.get("population", 0), reverse=True)
        cities_by_country[c_code] = c_cities_sorted

    return gc, country_map, sorted_countries, cities_by_country

gc, country_map, country_list, cities_by_country = load_geo_data()

@st.cache_resource
def get_tz_finder() -> TimezoneFinder:
    return TimezoneFinder()

tf = get_tz_finder()

def get_utc_julian_day(date_obj: date, time_obj: time, tz_str: str) -> float:
    local_tz = pytz.timezone(tz_str)
    dt = datetime.combine(date_obj, time_obj)
    local_dt = local_tz.localize(dt)
    utc_dt = local_dt.astimezone(pytz.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0,
    )

# ==========================================
# 2. إعدادات واجهة المستخدم (Streamlit)
# ==========================================
st.set_page_config(
    page_title="برنامج تحديد الطالع",
    layout="wide",
)

st.title("🌟 نظام تحديد الطالع المرجح من النقطة الشرقية - برمجة الفلكي استرو رادار")
st.markdown("النقطة الشرقية هي الدرجة من البروج التي تقاطع الأفق الشرقي مع خط الاستواء السماوي. وهي تمثل 'طالعاً استوائياً' مستقلاً عن خط العرض الجغرافي، وتُحسب رياضياً بدلالة الزمن النجمي المحلي والمطلع المستقيم لوسط السماء.")

# ----------------- لوحة المدخلات الجانبية -----------------
st.sidebar.header('📋 بيانات المولود والموقع الجغرافي')

name_input = st.sidebar.text_input('اسم المستفيد', 'مولود جديد')
birth_date = st.sidebar.date_input(
    "تاريخ الميلاد:", min_value=date(1900, 1, 1), max_value=date.today()
)
selected_country_name = st.sidebar.selectbox('دولة الميلاد', country_list)
c_code = country_map.get(selected_country_name)

country_cities = cities_by_country.get(c_code, [])
if not country_cities:
    country_cities = [{'name': 'المدينة المركزية', 'latitude': 33.5138, 'longitude': 36.2765, 'population': 1000000}]

city_options = [f"{c['name']} (السكان: {c.get('population', 0):,})" for c in country_cities]
selected_city_str = st.sidebar.selectbox('مدينة الميلاد (مرتبة بالكثافة السكانية)', city_options)

selected_city_obj = country_cities[city_options.index(selected_city_str)]
city_lat = selected_city_obj['latitude']
city_lon = selected_city_obj['longitude']

auto_tz = tf.timezone_at(lng=city_lon, lat=city_lat)
if not auto_tz:
    auto_tz = 'UTC'

timezone_str = st.sidebar.text_input('المنطقة الزمنية (تلقائي أو تعديل يدوي)', value=auto_tz)

st.sidebar.info(
    f'📍 الإحداثيات المختارة:\nخط العرض: {city_lat}° | خط الطول: {city_lon}°\n🌍 المنطقة الزمنية: {timezone_str}'
)

time_intervals = [
    'من 10 ص - 1 م',
    'من 1 م - 4 م',
    'من 4 م - 7 م',
    'من 7 م - 10 م',
    'من 10 م الى 1 فجرا',
    'من 1 فجرا - 4 فجرا',
    'من 4 فجرا - 7 ص',
    'من 7 ص الى 10 ص',
]
selected_interval = st.sidebar.selectbox(
    'الفترة الزمنية المتوقعة (فترات 3 ساعات)', time_intervals
)

zodiacs = [
    'الحمل (Aries)', 'الثور (Taurus)', 'الجوزاء (Gemini)', 'السرطان (Cancer)',
    'الأسد (Leo)', 'العذراء (Virgo)', 'الميزان (Libra)', 'العقرب (Scorpio)',
    'القوس (Sagittarius)', 'الجدي (Capricorn)', 'الدلو (Aquarius)', 'الحوت (Pisces)'
]

def format_degree(deg):
    sign_idx = int(deg // 30) % 12
    rem = deg % 30
    d_int = int(rem)
    m_int = int((rem - d_int) * 60)
    return f"{d_int}° {m_int:02d}' - {zodiacs[sign_idx]}"

# ==========================================
# 3. محرك الحساب والتحليل الفلكي
# ==========================================
if st.button('🚀 احسب الطالع المرجح ونقطة EP'):
    interval_map = {
        'من 10 ص - 1 م': (10.0, 13.0),
        'من 1 م - 4 م': (13.0, 16.0),
        'من 4 م - 7 م': (16.0, 19.0),
        'من 7 م - 10 م': (19.0, 22.0),
        'من 10 م الى 1 فجرا': (22.0, 1.0),
        'من 1 فجرا - 4 فجرا': (1.0, 4.0),
        'من 4 فجرا - 7 ص': (4.0, 7.0),
        'من 7 ص الى 10 ص': (7.0, 10.0),
    }

    start_h, end_h = interval_map[selected_interval]
    
    # اختيار منتصف الفترة الزمنية ليكون هو الوقت المرجح بدقة قطعية
    mid_h = (start_h + end_h) / 2.0
    h_local = mid_h % 24
    current_date = birth_date
    if mid_h >= 24:
        current_date = birth_date + timedelta(days=1)
    elif mid_h < 0:
        current_date = birth_date - timedelta(days=1)

    hour_int = int(h_local)
    minute_int = int((h_local - hour_int) * 60)
    time_obj = time(hour=hour_int, minute=minute_int, second=0)

    try:
        jd = get_utc_julian_day(current_date, time_obj, timezone_str)
        cusps, ascmc = swe.houses(jd, city_lat, city_lon, b'P')
        
        asc_deg = ascmc[0]  # الطالع
        ep_deg = ascmc[4]   # النقطة الشرقية EP

        asc_str = format_degree(asc_deg)
        ep_str = format_degree(ep_deg)
        time_str = f"{int(h_local%24):02d}:{minute_int:02d}"

        st.success(f"✅ تم حساب الطالع المرجح بنجاح للمستفيد: **{name_input}**")
        st.markdown("---")
        
        # عرض النتائج في واجهة ستريمليت
        st.subheader("⭐ النتيجة النهائية: الطالع المرجح القطعي ونقطة EP")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"### 🌅 الطالع المرجح (ASC)")
            st.markdown(f"**الوقت المقدر (المنتصف):** {time_str}")
            st.markdown(f"**درجة الطالع:** {asc_str}")
        with col2:
            st.markdown(f"### 📍 النقطة الشرقية (East Point / EP)")
            st.markdown(f"**موقع EP:** تقع النقطة الشرقية في **{ep_str}**")
            st.markdown(f"**التوافق الفلكي:** تتكامل بدقة مع أوتاد الخريطة والفترة المختارة.")

        # توليد محتوى تقرير الـ HTML القابل للطباعة
        html_report = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>تقرير الخريطة الفلكية - {name_input}</title>
            <style>
                body {{ font-family: 'Amiri', Tahoma, Arial, sans-serif; background: #f9f9f9; color: #333; direction: rtl; padding: 20px; }}
                .container {{ max-width: 800px; margin: auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h1 {{ text-align: center; color: #000; border-bottom: 2px solid #3182ce; padding-bottom: 10px; }}
                .section {{ margin-top: 20px; padding: 15px; background: #edf2f7; border-radius: 8px; }}
                .highlight {{ font-weight: bold; color: #000; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th, td {{ border: 1px solid #cbd5e0; padding: 10px; text-align: right; }}
                th {{ background-color: #2b6cb0; color: #000; }}
                .footer {{ text-align: center; margin-top: 30px; font-size: 0.9em; color: #718096; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>تقرير التنجيم الغربي المتقدم</h1>
                <div class="section">
                    <h3>بيانات المستفيد والموقع الجغرافي</h3>
                    <p><strong>الاسم:</strong> {name_input}</p>
                    <p><strong>تاريخ الميلاد:</strong> {birth_date.strftime('%Y-%m-%d')}</p>
                    <p><strong>الدولة / المدينة:</strong> {selected_country_name} - {selected_city_str}</p>
                    <p><strong>الإحداثيات الجغرافية:</strong> خط عرض {city_lat}°، خط طول {city_lon}°</p>
                    <p><strong>المنطقة الزمنية:</strong> {timezone_str}</p>
                    <p><strong>الفترة الزمنية المختارة:</strong> {selected_interval}</p>
                </div>
                
                <div class="section">
                    <h3>النتائج الفلكية المرجحة</h3>
                    <table>
                        <tr>
                            <th>المؤشر الفلكي</th>
                            <th>الوقت المقدر (المنتصف)</th>
                            <th>الدرجة والبرج</th>
                        </tr>
                        <tr>
                            <td>الطالع المرجح (Ascendant)</td>
                            <td>{time_str}</td>
                            <td class="highlight">{asc_str}</td>
                        </tr>
                        <tr>
                            <td>النقطة الشرقية (East Point - EP)</td>
                            <td>{time_str}</td>
                            <td class="highlight">تقع في {ep_str}</td>
                        </tr>
                    </table>
                </div>
                
                <div class="footer">
                    <p>تم استخراج هذا التقرير آلياً عبر نظام المستشار الفلكي المتقدم باستخدام الفلك السويسري (Swiss Ephemeris).</p>
                </div>
            </div>
        </body>
        </html>
        """

        st.markdown("---")
        st.subheader("📄 تصدير وطباعة التقرير")
        st.download_button(
            label="📥 تحميل التقرير الكامل بصيغة HTML (قابل للطباعة)",
            data=html_report,
            file_name=f"astrology_report_{name_input.replace(' ', '_')}.html",
            mime="text/html"
        )

    except Exception as ex:
        st.error(f"حدث خطأ أثناء الحساب الفلكي: {str(ex)}")
