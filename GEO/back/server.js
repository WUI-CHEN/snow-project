const express = require("express");  // require() 是 Node.js 裡用來「引入外部模組」的函數
const path = require("path"); 
const cors = require("cors");  // cors 讓前端可以跨網域連到我的伺服器
const app = express();  // 建立一個 Express 應用程式
require('dotenv').config();  // 使用 dotenv 這個套件來讀取 Env
const ESRI_API_KEY = process.env.ESRI_API_KEY;  // 從 .env 檔案讀取 ESRI_API_KEY 的內容

app.use(express.json());   // express.json()：讓伺服器可以讀懂 JSON 格式的請求內容
app.use(express.static(__dirname));

app.use(cors({ origin: "*" }));   // cors({ origin: "*" })：允許「任何網站」都能呼叫這個 API
app.use('/static', express.static(path.join(__dirname, "/../../static")));
app.use(express.static(path.join(__dirname, "/../front")));  // SNOW/GEO/front 資料夾



//fetch 是一個網路請求函式，用來對外部伺服器（例如 API）送出請求（GET、POST 等），然後取得回應。
const fetch = (...args) => import('node-fetch').then(({ default: fetch }) => fetch(...args));

const PORT = 8080;

app.get('/static/css/main.css', (req, res) => {
  res.sendFile(__dirname + '/static/css/main.css');
});

// 地理編碼
app.post("/api/geocode", async (req, res) => {
  console.log("收到 geocode 請求");
  const { address } = req.body;  // 從前端傳來的資料中，解構出 address 欄位
  if (!address) return res.status(400).json({ error: "請輸入地址" });  
  //res.status(400): 設定 HTTP 狀態碼為 400   // .json({ error: "..." }): 回傳 JSON 格式的錯誤訊息

  const url = `https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine=${encodeURIComponent(address)}&maxLocations=1&token=${ESRI_API_KEY}`;

  try {
    const response = await fetch(url);  // await: 等待非同步完成（不會馬上往下跑）
    const data = await response.json();  // 把回應內容解析成 JSON 物件

    if (!data.candidates || data.candidates.length === 0) {  // 如果沒有找到地點候選結果，
      return res.status(404).json({ error: "找不到地點" });     // 就回傳 HTTP 404 錯誤，告訴使用者這個地址找不到
    }  

    res.json({ location: data.candidates[0].location });  // 把第一個候選地點的經緯度回傳給前端
  } catch (err) {                                    // 如果上述過程中有錯誤（例如網路斷線、API 爛掉），
    res.status(500).json({ error: "地理編碼錯誤" });   // 就回傳 500 錯誤
  }
});

// 路線查詢
app.post("/api/route", async (req, res) => {
  console.log("收到 route 請求");
  const { stops, barriers } = req.body;    // 使用 解構賦值，把前端傳來的 JSON 裡的 stops 和 barriers 抓出來
  if (!stops || stops.length !== 2) {      // 如果 stops 沒有傳來，或傳來的不是兩個點，就回傳錯誤
    return res.status(400).json({ error: "請傳入兩個地點" });
  }

  const payload = {        // 要送給 ArcGIS 的資料格式，是 ESRI 的路線規劃服務 API 所要求的格式
    stops: {
      features: stops.map((p, i) => ({        // 把兩個地點變成 GeoJSON 格式，ArcGIS 要求地點要是 features 陣列
        geometry: {                           // 每個地點都包含經緯度和名稱
          x: p.x,     // p.x, p.y: 是前端送來的地點經緯度
          y: p.y,
          spatialReference: { wkid: 4326 }  // wkid: 4326: 表示經緯度坐標系（WGS 84）
        },
        attributes: { Name: `P${i}` }
      })),
      spatialReference: { wkid: 4326 }
    },
    ...(barriers && {          // 如果 barriers 存在，就把 polygonBarriers 加進來。如果沒有避災區，就不加
      polygonBarriers: {
        features: barriers.map((poly, i) => ({
          geometry: { rings: [poly], spatialReference: { wkid: 4326 } },
          attributes: { Name: `B${i}` }
        }))
      }
    }),
    returnRoutes: true,    // returnRoutes: 要求回傳路線資訊
    f: "json",             // 明確指定回傳格式是 JSON，否則預設會是 HTML
    token: ESRI_API_KEY  // token: API 金鑰（用來驗證你有權限使用這個服務）
  };

  const params = new URLSearchParams();      // 把 payload 的所有欄位轉成 HTTP 表單格式（key=value
  for (const key in payload) {
    params.append(key, typeof payload[key] === 'object' ? JSON.stringify(payload[key]) : payload[key]);
  }  // 把每一個 payload 裡的欄位加入 params，如果是物件，要先用 JSON.stringify 轉成字串

  // ArcGIS 的「全球路線規劃」API 位置
  const url = "https://route.arcgis.com/arcgis/rest/services/World/Route/NAServer/Route_World/solve";

  try {
    const response = await fetch(url, {   // 使用 fetch 發送 POST 請求
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params
    });

    const text = await response.text();    // 伺服器回傳的結果用 text() 先讀取，因為不知道是不是 JSON
    console.log("ESRI 路線回傳：", text.substring(0, 500));

    let data;
    try {
      data = JSON.parse(text);  // 如果 text 是 JSON，會成功解析
    } catch (e) {
      console.error("JSON 解析失敗，回傳的是 HTML：\n", text.substring(0, 500));
      return res.status(500).json({ error: "ESRI 回傳錯誤格式（不是 JSON）" });
    }

    res.json(data);  // 成功的話就把路線結果傳給前端，讓他畫在地圖上
  } catch (err) {
    console.error("路線查詢失敗：", err);
    res.status(500).json({ error: "路線查詢失敗" });
  }
});

app.listen(PORT, () => {
  console.log(`後端啟動：http://localhost:${PORT}`);
});
