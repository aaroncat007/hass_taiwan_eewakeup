# Taiwan EEW (台灣地震速報) Home Assistant 整合套件

這是一個專為 Home Assistant (HASS) 設計的自訂整合套件（Custom Component），對接 [臺灣地震速報網頁版](https://twearthquake.github.io/)，透過即時 API 輪詢接收台灣地震速報（EEW），以便在地震波抵達前執行超低延遲的避難自動化（例如：播放語音警報、關閉瓦斯閥門、開啟避難照明等）。

本套件已全面支援 **Home Assistant 整合設定流程 (Config Flow)**，使用者只需直接在 HASS UI 介面中新增整合並挑選縣市，無需手動修改 `configuration.yaml` 設定檔。

---

## 核心功能

*   **實時加密輪詢**：對接 `twearthquake.zapto.org:30007` 平台，採用與網頁版相同的 HMAC-SHA256 簽章演算法進行安全通訊（預設每 1.5 秒更新一次）。
*   **整合設定介面 (Config Flow)**：支援多實體安裝。您可以在 UI 中直接下拉選擇欲監測的縣市（例如台北市、花蓮縣等），並自訂輪詢間隔。您可以為不同縣市分別新增此整合，其感測器實體將會完全隔離，互不干涉。
*   **低延遲事件派發**：除了感測器實體狀態更新外，套件收到地震預警時會立刻向 Home Assistant 的 Event Bus 廣播自訂事件 `taiwan_eew_event`。這避開了資料庫寫入磁碟的延遲，達到亞毫秒級的極速響應。
*   **家庭儀表板友善 (主狀態為中文震度)**：感測器的主狀態會保持最直覺的原始震度字串（如 `"5弱"`, `"5強"`, `"6弱"`, `"6強"`），讓您在 Lovelace Dashboard 儀表板上能一眼看懂。
*   **自動化判斷友善 (屬性內含 `intensity_value`)**：將中文震度自動對應並轉換成數值浮點數（如 `5弱` $\rightarrow$ `5.0`，`5強` $\rightarrow$ `5.5`），並放置於屬性 `intensity_value` 中，讓自動化可以直接進行 `>= 5.0` 等數值大小判斷。
*   **自動計算震央距離 (`distance_km`)**：自動讀取您 Home Assistant 中設定的家庭 GPS 座標（經緯度），並在收到預報時透過半正矢（Haversine）公式即時計算出**震央與您家中的直線距離**。
*   **自動復歸機制**：當警報結束或超過 120 秒未收到更新時，感測器會自動將狀態歸零（主狀態變回 `"0.0"`，`intensity_value` 變回 `0.0`），以確保下一次地震能成功觸發自動化中的「數值跨越（Numeric State）」條件。

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

### 3. 多地點監測（選用）
如果您希望同時監測多個縣市，可以重複上述「新增整合」步驟，並選擇不同的縣市。系統將會自動建立多個獨立感測器實體（例如 `sensor.taiwan_eew_sensor_taipei` 與 `sensor.taiwan_eew_sensor_hualien`）。

---

## 提供的感測器資訊

### 感測器實體：`sensor.taiwan_eew_sensor_<縣市英文小寫>`
*   **主狀態 (State / Native Value)**：預估震度（字串型態，如 `"5弱"`, `"5強"`, `"6弱"`, `"6強"`，無警報時為 `"0.0"`）。

### 感測器屬性 (Attributes)
| 屬性名稱 | 資料型態 | 說明 |
| :--- | :--- | :--- |
| `intensity_value` | `float` | 震度之數值對應（例如 `5弱` (5-) 為 `5.0`，`5強` (5+) 為 `5.5`，`6弱` (6-) 為 `6.0` 等） |
| `arrival_time_seconds` | `int` | 地震波預估抵達秒數 |
| `epicenter_location` | `str` | 震央位置名稱（例如："花蓮近海"） |
| `distance_km` | `float` | 震央與您在 HASS 中設定的家庭坐標之間的直線距離（公里） |
| `event_id` | `str` | 地震事件唯一識別 ID（由地震發生時間標記） |
| `report_num` | `int` | 該地震事件的警報更新序號 |
| `monitored_location` | `str` | 該實體監測的縣市代碼（例如："Taipei"） |

---

## 自動化設定範例

### 範例 A：事件觸發（推薦 🌟 - 超低延遲，適用播報與多重修正）
此方式會在收到**每一次**警報修正時觸發，能動態播報最新的倒數秒數與震度。自動化可利用 `trigger.event.data.location` 來過濾特定的監測地點。

```yaml
alias: "地震預警 - 即時語音播報與避難指引"
trigger:
  - platform: event
    event_type: taiwan_eew_event
condition:
  # 1. 確保不是收到「解除/歸零」信號
  - condition: template
    value_template: "{{ trigger.event.data.clear is not defined }}"
  # 2. 僅過濾台北市的地震預警
  - condition: template
    value_template: "{{ trigger.event.data.location == 'Taipei' }}"
  # 3. 僅在地震距離小於 150 公里時觸發
  - condition: template
    value_template: "{{ trigger.event.data.distance_km is not defined or trigger.event.data.distance_km | float < 150.0 }}"
action:
  - service: tts.google_translate_say
    target:
      entity_id: media_player.living_room_speaker
    data:
      message: >-
        警告，台北市偵測到地震預警！震央位於 {{ trigger.event.data.epicenter_location }}，
        預估震度為 {{ trigger.event.data.magnitude }}，
        大約還有 {{ trigger.event.data.arrival_time_seconds }} 秒抵達，請做好防震準備。
```

### 範例 B：狀態跨越觸發（適用於單次開關控制）
利用感測器屬性 `intensity_value` 作為數值條件。當數值大於 `4.9`（意即達 **5弱** 或以上）時觸發。

```yaml
alias: "台北地震預警 - 5級以上自動關閉瓦斯"
trigger:
  - platform: numeric_state
    entity_id: sensor.taiwan_eew_sensor_taipei
    attribute: intensity_value
    above: 4.9  # 4.9 以上會包含 5.0 (5弱)、5.5 (5強) 等，即代表 5 級以上
condition:
  # 可選條件：只在震央距離我家 100 公里內才切斷瓦斯
  - condition: numeric_state
    entity_id: sensor.taiwan_eew_sensor_taipei
    attribute: distance_km
    below: 100
action:
  - service: switch.turn_off
    target:
      entity_id: switch.main_gas_valve
```
