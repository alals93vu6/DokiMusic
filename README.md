# DokiMusic / KeyScore

Windows 本機音樂轉遊戲按鍵工具：WebView 介面、MP3 樂器分離與轉譜、主旋律選取，以及可重新匯入 Python 的樂譜編輯器。

支援鋼琴／大提琴、15 個遊戲按鍵、最多 8 音和弦、独立長短音、框選批次編輯、游標試播與拖曳試聽。匯出播放器使用 Windows SendInput，執行時預設倒數 5 秒，Esc 或切換焦點可停止。

## 專案結構

- `outputs/KeyScore/`：應用程式、WebView、播放器模板與文件。
- `work/keyscore/test_*`：回歸測試。
- `work/keyscore/fetch_audiosep.py`、`prepare_audiosep.py`：模型下載與準備。
- `work/keyscore/models/`、`data/`：本機模型與暫存，不納入 Git。

保留此結構，避免破壞模型與資料目錄定位。

## Windows 安裝與啟動

需要 Python 3.10 及 Microsoft Edge WebView2 Runtime。在專案根目錄執行：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r outputs/KeyScore/requirements.txt
.\.venv\Scripts\python.exe outputs/KeyScore/app.py
```

也可雙擊根目錄 `KeyScore.bat`。若沿用其他位置的環境，可在根目錄建立 `runtime-path.txt`，第一行填入 `pythonw.exe` 的完整路徑；此檔不會提交。`.venv` 優先於該本機設定。

混音分離需先準備 AudioSep 模型，純獨奏模式不需要它：

```powershell
.\.venv\Scripts\python.exe -m pip install transformers==4.46.3 requests
.\.venv\Scripts\python.exe work/keyscore/fetch_audiosep.py
.\.venv\Scripts\python.exe work/keyscore/prepare_audiosep.py
```

第一次下載原權重約 1.3 GB，正常分析在本機完成。GPU 需相容的 PyTorch CUDA 版本；也支援 CPU。`requirements-lock.txt` 是開發機環境快照，包含 CUDA 與測試工具，非所有電腦的通用安裝清單。

Git 不包含模型、使用者音訊或產出的演奏脚本；僅保留程式合成的短示範曲 `assets/demo.mp3`，可透過下列 integration 測試重新生成。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s work/keyscore -p test_core.py
.\.venv\Scripts\python.exe -m unittest discover -s work/keyscore -p test_score.py
.\.venv\Scripts\python.exe -m unittest discover -s work/keyscore -p test_melody.py
.\.venv\Scripts\python.exe work/keyscore/test_integration.py
node work/keyscore/test_editor_playback.cjs
```

前端測試另需 Node.js。混音整合／A–H benchmark 測試另需分離模型與 GeneralUser GS SoundFont；SoundFont 不在 Git 中。測試用取樣音色須自行取得官方 GeneralUser GS，將 sf2 放在 `work/keyscore/benchmark/GeneralUser-GS.sf2`，並安裝 `tinysoundfont` 後執行 `benchmark_isolation.py`。

## 文件與限制

- [使用說明](outputs/KeyScore/README.md)
- [架構與模型來源](outputs/KeyScore/ARCHITECTURE.md)
- [音訊驗證](outputs/KeyScore/VALIDATION.md)
- [編輯器驗證](outputs/KeyScore/EDITOR_VALIDATION.md)

主旋律選取是啟發式，混合樂器仍可能有殘音與漏音，並非完美轉譜。編輯器試播為合成音，不代表遊戲音色。第三方 AudioSep 程式授權保留在 `outputs/KeyScore/vendor/audiosep/LICENSE`。
