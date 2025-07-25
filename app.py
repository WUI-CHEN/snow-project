from flask import Flask, request, render_template, send_from_directory
import requests
from datetime import datetime, timezone, timedelta

app = Flask(__name__, static_folder='templates')

coord = {
    "hhs": (24.15, 121.27),
    "tps": (24.48, 121.53),
    "ys":  (23.47, 120.96),
    "sp":  (24.38, 121.03),
    "yms": (25.15, 121.55),
    "wl":  (24.37, 121.32),
    "t14j": (24.12, 121.27),
    "t8": (24.18,121.33),
    "t7": (24.42, 121.21),
    "t7j":(24.42, 121.36)
}

loc_names = {
    "hhs": "合歡山",
    "tps": "太平山",
    "ys":  "玉山",
    "sp":  "雪霸國家公園",
    "yms": "陽明山、七星山",
    "wl":  "武陵農場",
    "t14j": "台14甲線",
    "t8": "台8線",
    "t7": "台7線",
    "t7j": "台7甲線"
}

map_links = {
    "hhs": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=fea672521dfe414597bb73819fdee87f",
    "tps": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=e9e10c2abc134b5b96e89e98bbf9b24f",
    "ys": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=b035df9646804489989e754ca8a2494a",
    "sp": "https://archive.maps.arcgis.com/apps/configure-template/index.html?appid=2fc2d80fe8144ac7a13118341f242bae",
    "yms": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=38ade048ccb5409c8604d6d1d887e68d",
    "wl": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=f583791e3f514a659005eacb6a20c5a0",
    "t14j": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=f17b53fbf44d4294af12330a7349f0d5",
    "t8": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=0ee94777e4d24406824e3588824e00e8",
    "t7": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=7d2c06ef3c2844948c2ff104d66d2296",
    "t7j": "https://archive.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=be188814208b4c3785e090de2e066a53"
}

# 根據選擇的地點來分類風險
def get_location_type(loc_code):
    # 如果是台14甲線，則視為道路
    if loc_code in ["t14j", "t8", "t7","nz"]:
        return "road"
    else:
        return "mountain"
    
def get_weather_and_risks(loc_code, date):
    if loc_code not in coord:
        return None, "查無地點", None

    lat, lon = coord[loc_code]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,snowfall,visibility,dew_point_2m,rain",           
        "timezone": "Asia/Taipei",
        "start_date": date,
        "end_date": date
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        weather = response.json()
    except Exception as e:
        return None, f"無法取得氣象資料，請稍後再試。({str(e)})", None

    time_list = weather.get("hourly", {}).get("time", [])
    if not time_list:
        return None, "氣象資料格式錯誤", None

    time_objs = [datetime.fromisoformat(t).replace(tzinfo=timezone(timedelta(hours=8))) for t in time_list]

    # 把現在時間取整點（15:09 -> 15:00、16:58 -> 17:00）
    now = datetime.now(timezone(timedelta(hours=8)))
    rounded_hour = now.replace(minute=0, second=0, microsecond=0)
    if now.minute >= 30:
        rounded_hour += timedelta(hours=1)

    try:
        target_time = rounded_hour.replace(
            year=int(date[:4]),
            month=int(date[5:7]),
            day=int(date[8:10])
        )
    except Exception:
        return None, "日期轉換失敗", None

    diffs = [abs((t - target_time).total_seconds()) for t in time_objs]
    index = diffs.index(min(diffs))

    temperature = weather["hourly"]["temperature_2m"][index]
    humidity = weather["hourly"]["relative_humidity_2m"][index]
    rain_prob = weather["hourly"]["precipitation_probability"][index]
    rain = weather["hourly"]["rain"][index]
    snowfall = weather["hourly"]["snowfall"][index]
    visibility = weather["hourly"]["visibility"][index]
    dew_point = weather["hourly"]["dew_point_2m"][index]


    risks = []
    location_type = get_location_type(loc_code)

    if location_type == "mountain":
        if temperature < 0:
            risks.append("水管凍結風險")

        if visibility < 200:  #Visibility
            risks.append("濃霧風險")

        if rain_prob > 70:
            risks.append("降雨機率偏高，建議備雨具或延後行程")

        if snowfall > 0:
            risks.append(f"預計降雪量為 {snowfall} mm/hr，請注意道路結冰或封閉情況")

        traffic_light = "gray"     ### 山區沒燈號也定義一個值，否則return時會出錯
    
    else:
        overall_risk = None

        if temperature < 0 and (dew_point < 0 or humidity >= 70 ):
            overall_risk = "高風險"

        elif temperature > 5 or dew_point > 0 or humidity < 70 :
            overall_risk = "低風險"

        else:
            overall_risk = "中風險"

        risks.append(overall_risk)

        # 根據 overall_risk 決定燈號顏色
        if overall_risk == "高風險":
            traffic_light = "red"
        elif overall_risk == "中風險":
            traffic_light = "orange"
        else:
            traffic_light = "green"


    return {
        "temperature": temperature,
        "humidity": humidity,
        "rain_prob": rain_prob,
        "rain": rain,
        "snowfall": snowfall,
        "visibility": visibility,
        "dew_point":  dew_point,
        "risks": risks,
        "overall_risk": overall_risk if location_type == "road" else None,
        "location_type": location_type,
        "traffic_light" : traffic_light
    }, None, weather


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/story')
def story():
    return render_template('story.html')

@app.route('/generic')
def generic():
    return render_template('generic.html')

@app.route('/map-inquiry')
def map_inquiry():
    return send_from_directory('GEO/front', 'index.html')

@app.route("/result")
def result():
    loc_code = request.args.get("location")
    date = request.args.get("date")

    try:
        formatted_date = datetime.strptime(date, "%Y/%m/%d").strftime("%Y-%m-%d")
    except ValueError:
        return "日期格式錯誤", 400

    weather_data, error, _ = get_weather_and_risks(loc_code, formatted_date)


    if error:
        return error, 500

    location_type = weather_data["location_type"]
    traffic_light = weather_data["traffic_light"]
    map_url = map_links.get(loc_code, "")
    date_display = datetime.strptime(date, "%Y/%m/%d").strftime("%m/%d")


    return render_template("result.html",
                           location = loc_code,
                           location_name = loc_names.get(loc_code, loc_code),
                           temperature = weather_data["temperature"],
                           humidity = weather_data["humidity"],
                           rain_prob = weather_data["rain_prob"],
                           rain = weather_data["rain"],
                           snowfall = weather_data["snowfall"],
                           visibility = weather_data["visibility"],
                           dew_point = weather_data["dew_point"],
                           risks = weather_data["risks"],
                           overall_risk = weather_data["overall_risk"],
                           map_url = map_url,
                           date_display = date_display,
                           location_type = location_type,
                           traffic_light = traffic_light)
                           

if __name__ == "__main__":
    app.run(debug=True)
