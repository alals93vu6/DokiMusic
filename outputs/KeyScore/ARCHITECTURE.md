# 目標樂器分離實作

既有流程：pywebview → 本機檔案 → 獨立 worker → FFmpeg 解碼 → Basic Pitch ONNX → arrangement → Windows SendInput Python 匯出。

新增混音流程：32 kHz 單聲道解碼 → AudioSep 文字條件分離（目標與競爭樂器）→ 重疊相加 → 22.05 kHz 重採樣 → 依樂器 HPSS／頻譜遮罩 → 原 Basic Pitch → 訊號證據篩選 → 原編排與匯出。純獨奏分支仍直接解碼至 22.05 kHz 並使用原辨識設定。

`isolation.py` 提供 IAudioSourceIsolationService、分段 AudioSep 實作與 SignalEvidence；`isolation_profiles.py` 分別管理鋼琴和大提琴參數。HPSS 僅強化已分離的目標，沒有以固定頻帶判斷樂器。

證據包含目標／競爭訊號的諧波能量比、原混音保留量、相對能量、持續性、音符長度及 Basic Pitch 強度。大提琴同音片段只在能量沒有新起音時合併；快速重複音仍可能受此啟發式影響。現有 SendInput 掃描碼、5 秒倒數、和弦及各音獨立放開未改寫。

## 模型選擇與資源

採用 [AudioSep 官方模型](https://github.com/Audio-AGI/AudioSep)，因為文字條件可指定 piano 與 cello。一般 vocals/drums/bass/other 分軌不足以取得獨立大提琴軌；HPSS/EQ 也無法單獨辨認重疊音域的樂器。

沿用官方 ResUNet30 與 CLAP 文字投影，將固定樂器查詢預先計算；不需要在每次推論載入完整文字及音訊編碼器。原權重約 1.26 GB，執行用分離權重約 156 MB，查詢約 13 KB。版本、SHA256 與來源記錄於模型 manifest 及 vendor/audiosep/provenance.json。供應商程式的 MIT 授權保留於 vendor/audiosep/LICENSE；模型來源是官方 Hugging Face Space，後續若另行散布模型應一併核對模型端條款。

本機 RTX 3060 可用 CUDA；亦實作 CPU 路徑，限制 PyTorch 與 ONNX 使用 4 個執行緒。分離每窗 5 秒、每次前進 3 秒；辨識每段 30 秒加前後 1 秒。長檔仍持有全檔 waveform 與重疊緩衝，並非完全串流。GPU 不足時使用者可選 CPU 重試。

新增樂器時，需準備對應 CLAP 查詢向量、profile、UI 選項，以及該樂器的驗證資料；不能只新增名稱便宣稱支援。

## 已知未達成項目

完整三樂器混音仍有顯著殘音，未達文件「不大量轉入伴奏旋律」的理想驗收標準；目前降低誤判但不能保證目標音色識別。低於門檻會拒絕候選，然而模型對缺席樂器也可能輸出其他樂器，訊號證據不是可靠的存在性分類器。人聲、吉他及貝斯尚未有專項驗證。下一步需要真實分軌資料評估與更可靠的樂器存在性／音符歸屬模型，不能靠不斷提高門檻解決。
