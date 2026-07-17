# Taiwan EEW (台灣地震速報) Home Assistant 整合套件

這是一個專為 Home Assistant (HASS) 設計的自訂整合套件（Custom Component），對接 [臺灣地震速報網頁版](https://twearthquake.github.io/)，透過即時 API 輪詢接收台灣地震速報（EEW），以便在地震波抵達前執行超低延遲的避難自動化（例如：播放語音警報、關閉瓦斯閥門、開啟避難照明等）。

本套件已全面支援 **Home Assistant 整合設定流程 (Config Flow)**，使用者只需直接在 HASS UI 介面中新增整合並挑選縣市，無需手動修改 `configuration.yaml` 設定檔。

---

## 核心功能

*   **實時加密輪詢**：對接 `twearthquake.zapto.org:30007` 平台，採用與網頁版相同的 HMAC-SHA256 簽章演算法進行安全通訊（預設每 1.5 秒更新一次）。
*   **整合設定介面 (Config Flow)**：支援多實體安裝。您可以在 UI 中直接下拉選擇欲監測的縣市（例如台北市、花蓮縣等），並自訂輪詢間隔。您可以為不同縣市分別新增此整合，其感測器實體將會完全隔離，互不干涉。
*   **低延遲事件派發**：除了感測器實體狀態更新外，套件收到地震預警時會立刻向 Home Assistant 的 Event Bus 廣播自訂事件 `taiwan_eew_event`。這避開了資料庫寫入磁碟的延遲，達到亞毫秒級的極速響應。
*   **家庭儀表板友善 (雙感測器設計)**：
    *   **即時警告感測器 (`sensor.taiwan_eew_warning_<縣市>`)**：主狀態保持最直覺的中文預估震度（如 `"5弱"`, `"5強"`，無警報時為 `"0級"`），在無警報時會自動歸零，以利自動化觸發。
    *   **最新地震報告感測器 (`sensor.taiwan_eew_last_report_<縣市>`)**：主狀態為最近一次發生的地震震央（如 `"海外地震"`, `"花蓮近海"`），**永遠不會歸零**，專門用來在 Dashboard 面板上顯示最新地震的細節。
*   **自動計算震央距離 (`distance_km`)**：自動讀取您 Home Assistant 中設定的家庭 GPS 座標（經緯度），並在收到預報時透過半正矢（Haversine）公式即時計算出**震央與您家中的直線距離**。

---

## 資料來源與免責宣告

本套件之即時地震速報資料來源對接自 **[臺灣地震速報網頁版](https://twearthquake.github.io/)**。

> [!WARNING]  
> **免責聲明**  
> * 本套件所取得之地震預警資訊可能因網路延遲、感測器誤差或第三方伺服器維護而有時間差或遺漏。
> * **切勿**將本套件作為唯一的生命安全避難警報來源。請務必以交通部中央氣象署（CWA）官方發布之強震即時警報（PWS 手機災防告警細胞簡訊、電視警報）為準。
> * 本套件僅適合作為連動智慧家居設備（如開啟電燈、關閉電器）的輔助工具。

---

## 安裝與設定步驟

### 1. 複製檔案
將本專案中的 `custom_components/taiwan_eew/` 資料夾複製到您的 Home Assistant 設定目錄中的 `custom_components/` 底下。

### 2. UI 新增整合
1. 重新啟動 Home Assistant。
2. 前往 **設定** -> **裝置與服務** -> **新增整合**。
3. 搜尋並選擇 **Taiwan EEW**。
4. 在跳出的設定視窗中：
   * **所在地 (Location)**：從下拉選單中挑選您的縣市（例如 `台北市 (Taipei)` 或 `花蓮縣 (Hualien)`）。
   * **輪詢間隔 (Poll Interval)**：自訂 API 請求間隔（預設 1.5 秒）。
5. 點擊送出即可完成安裝。

---

## 提供的感測器資訊

當您為某個地區新增此整合後，該**裝置（Device）**下會自動生成以下兩個獨立感測器：

### 1. 即時警告感測器：`sensor.taiwan_eew_warning_<縣市英文小寫>`
監測即時的地震速報（EEW），警報結束後會自動復歸。
*   **主狀態 (State)**：中文預估震度（如 `"5弱"`, `"5強"`, `"0級"`）。

#### 屬性 (Attributes)
| 屬性名稱 | 資料型態 | 語系 | 說明 |
| :--- | :--- | :--- | :--- |
| `預估震度` | `str` | 中文 | 預估震度中文名稱（如 `"5弱"`, `"0級"`） |
| `震度數值` | `float` | 中文 | 數值化震度值（例如 `5弱` 為 `5.0`，`5強` 為 `5.5`，無警報為 `0.0`） |
| `預估波抵達秒數` | `int` | 中文 | 地震波預估抵達所在地之倒數秒數 |
| `震央地點` | `str` | 中文 | 震央位置名稱（例如："花蓮近海"） |
| `震央距離_公里` | `float` | 中文 | 震央與您家庭 GPS 座標之間的直線距離（公里） |
| `是否為演習` | `str` | 中文 | 是否為防災演習資料（`"是"` 或 `"否"`） |
| `intensity_value` | `float` | 英文 | 數值化震度，**供自動化條件判定使用** |
| `arrival_time_seconds` | `int` | 英文 | 地震波預估抵達秒數 |
| `distance_km` | `float` | 英文 | 震央直線距離（公里） |

---

### 2. 最新報告感測器：`sensor.taiwan_eew_last_report_<縣市英文小寫>`
儲存中央氣象署發布之最近一次有感地震報告（歷史紀錄，不隨警報結束而清空）。
*   **主狀態 (State)**：最近一次地震的震央名稱（如 `"海外地震"`, `"花蓮縣秀林鄉"`）。

#### 屬性 (Attributes)
| 屬性名稱 | 資料型態 | 語系 | 說明 |
| :--- | :--- | :--- | :--- |
| `震央地點` | `str` | 中文 | 震央位置名稱 |
| `芮氏規模` | `float` | 中文 | 芮氏地震規模大小（例如 `7.4`） |
| `震源深度_公里` | `float` | 中文 | 地震震源深度（公里） |
| `最大震度` | `str` | 中文 | 全台觀測到的最大震度（例如 `"6弱"`, `"5強"`） |
| `地震發生時間` | `str` | 中文 | 地震發生日期與時間（例如 `"2026-07-17 22:49:00"`） |
| `震央緯度` | `float` | 中文 | 震央的緯度座標 |
| `震央經度` | `float` | 中文 | 震央的經度座標 |
| `海嘯警報` | `str` | 中文 | 是否伴隨海嘯警報發布（`"是"` 或 `"否"`） |
| `海嘯報告內容` | `str` | 中文 | 海嘯警報之詳細文字報告 |

---

## 廣播事件資料結構 (`taiwan_eew_event`)
當警報發布時，套件會立刻向 Event Bus 發送 `taiwan_eew_event`。其事件資料（`trigger.event.data`）格式如下：
```json
{
  "magnitude": "5-",
  "arrival_time_seconds": 12,
  "epicenter_location": "花蓮近海",
  "latitude": 23.9,
  "longitude": 121.6,
  "event_id": "2026-07-17 21:50:00",
  "report_num": 1,
  "scale": 5.2,
  "depth": 10.0,
  "max_level": "5-",
  "is_drill": false,
  "time": "2026-07-17 21:50:00",
  "has_tsunami": false,
  "tsunami_report": "",
  "intensity_value": 5.0,
  "location": "Taipei"
}
```

---

## 自動化設定範例

### 範例 A：事件觸發（推薦 🌟 - 超低延遲，適用避難連動）
這項方法完全繞過了資料庫寫入延遲，為**避難核心自動化（如關閉瓦斯、打開大門）之首選**。
您可以直接在條件中讀取 `trigger.event.data.intensity_value` 來進行震度門檻過濾。

```yaml
alias: "地震預警 - 5級以上自動關閉瓦斯"
trigger:
  - platform: event
    event_type: taiwan_eew_event
condition:
  # 1. 確保不是收到「解除/歸零」信號 (無警報時 intensity_value 為 0.0)
  - condition: template
    value_template: "{{ trigger.event.data.clear is not defined }}"
  # 2. 僅過濾特定縣市（例如台北市 Taipei）
  - condition: template
    value_template: "{{ trigger.event.data.location == 'Taipei' }}"
  # 3. 透過數值化震度判定：當預估震度達 5弱 (5.0) 或以上時執行
  - condition: template
    value_template: "{{ trigger.event.data.intensity_value | float >= 5.0 }}"
action:
  - service: switch.turn_off
    target:
      entity_id: switch.main_gas_valve
```

### 範例 B：狀態跨越觸發（適用於一般 Lovelace 通知）
利用即時警告感測器屬性 `intensity_value` 作為數值條件。當數值大於 `4.9`（意即達 **5弱** 或以上）時觸發。

```yaml
alias: "台北地震預警 - 5級以上發送手機通知"
trigger:
  - platform: numeric_state
    entity_id: sensor.taiwan_eew_warning_taipei
    attribute: intensity_value
    above: 4.9  # 4.9 以上會包含 5.0 (5弱)、5.5 (5強) 等，即代表 5 級以上
condition:
  # 可選條件：只在震央距離我家 150 公里內才發送通知
  - condition: numeric_state
    entity_id: sensor.taiwan_eew_warning_taipei
    attribute: distance_km
    below: 150
action:
  - service: notify.notify
    data:
      title: "🚨 地震警報 (台北監測)"
      message: "預估震度達到 5級 以上，地震波預估於 {{ state_attr('sensor.taiwan_eew_warning_taipei', '預估波抵達秒數') }} 秒後抵達！"
```
