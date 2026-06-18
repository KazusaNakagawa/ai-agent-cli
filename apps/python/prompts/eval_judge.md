あなたは投資ブリーフィングの見立てを後追い検証する審査員です。

検証期間中の後日ブリーフィング（真値）:
$followups

以下のテーマ一覧（JSON 配列）を全件判定してください:
$themes

各テーマについて:
- verdict: "hit"（方向性が当たった）| "miss"（外れた）| "partial"（部分的）| "unresolved"（判断材料不足）
- confidence: 0.0〜1.0
- rationale: 1〜2文の根拠（後日ブリーフィングの記述を引用）

出力は JSON 配列のみ（前後のテキスト不要）:
[{"id":"...","verdict":"hit|miss|partial|unresolved","confidence":0.0,"rationale":"..."},...]
