import json
from pathlib import Path

work=Path(__file__).resolve().parent
app=work.parents[1]/'outputs'/'KeyScore'
lines=['# v0.2 驗證結果','',
'2026-09-11。本機 RTX 3060、Python 3.10、AudioSep + Basic Pitch ONNX。',
'測試為 GeneralUser GS SoundFont 取樣音色合成後編碼為 MP3；每曲 14 秒。第一組有鋼琴和弦與大提琴長音，第二組改旋律並提高伴奏增益 35%。不是實際錄音資料集，也不是遊戲內演奏驗證。','',
'前：原獨奏分析器直接分析混音。後：新增分離、強化與證據篩選，均在遊戲音域映射前計算。FP 包含錯誤音符及重複切碎片段；完全相同 MIDI 音高、起音差 ≤150 ms 才匹配。音高 precision/recall 以 20 ms 格點計算。起音與時長 MAE 只計匹配音；SoundFont 放鍵後尾音會增加相對 MIDI 時長的誤差。','']
for file,title in [('metrics.json','A–H 基準'),('holdout_metrics.json','第二組旋律與較強伴奏')]:
    data=json.loads((work/'benchmark'/file).read_text(encoding='utf-8'))
    lines += ['## '+title,'','各欄皆為「前 → 後」。','',
      '|案例／目標|FP|漏音|音高 precision|音高 recall|起音 MAE ms|時長 MAE ms|',
      '|---|---:|---:|---:|---:|---:|---:|']
    for item in data:
        a,b=item['solo'],item['mixed']
        label=item['case']+' '+item['target']+' / '+'+'.join(item['instruments'])
        cells=[f'{a[k]} → {b[k]}' for k in ['false_positive','missed','frame_pitch_precision','frame_pitch_recall','onset_mae_ms','duration_mae_ms']]
        lines.append('|'+label+'|'+'|'.join(cells)+'|')
    lines.append('')
lines += ['## 結論與範圍','',
'鋼琴＋鼓及大提琴＋鼓改善明顯；兩組獨奏保留全部目標音。完整三樂器合奏仍有殘音，音高 precision 改善有限，尚未达到可靠排除伴奏的驗收目標。部分雙樂器案例有額外漏音。此版本可供試用，不能宣稱分離準確率已達產品級。','',
'14 秒基準曲，GPU 分離約 0.6–0.9 秒，完整混音流程暖機後約 3–4 秒（不同程序啟動與首次 JIT 載入會更久）。同一 B 曲 CPU 分離 18.87 秒。只代表本機短曲，不能直接外推所有曲長或其他硬體。','',
'## 功能檢查','',
'- 6 項既有編排／匯出單元測試通過，包括和弦、放鍵與切換焦點清理；鍵盤 API 使用替身。',
'- 4 項分離單元測試通過：長音合併／新起音保留、訊號證據、缺模型錯誤與選項驗證。',
'- 實際 MP3 獨奏 API、鋼琴／大提琴、速度與聲部限制、匯出腳本 --check、取消通過。',
'- 實際混音 API、快取沿用／切換失效、CPU 推論、分離途中取消通過。',
'- 40 秒跨分段音訊、無聲檔與損壞檔錯誤處理通過。',
'- WebView 已啟動並目視確認 v0.2 選項及版面；使用者按 Esc 停止介面操作，因此未完成滑鼠逐項互動檢查。',
'- 未向遊戲發送實際按鍵。','',
'可重跑腳本位於 work/keyscore：test_core.py、test_isolation.py、test_integration.py、test_audio_edges.py、test_mixed_integration.py、benchmark_isolation.py。--reuse 只重用基準原流程結果與音訊，仍重跑 mixed。']
(app/'VALIDATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
