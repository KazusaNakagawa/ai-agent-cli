# Workspace mermaid レンダリング対応 設計

## 背景・目的

Workspace 画面（`apps/web/components/screens/WorkspaceScreen.tsx`）で Markdown ファイルをプレビューすると、```mermaid コードフェンスがシンタックスハイライトされたテキストとしてそのまま表示され、図としてレンダリングされない。mermaid 記法のブロックを実際の図として描画できるように改善する。

## 適用範囲

`apps/web/components/ui/MarkdownView.tsx` は Workspace / Briefing / Journal / Chat の各画面で共用されている。mermaid 対応はこの共通コンポーネントに実装し、利用箇所すべてで自動的に恩恵を受けられるようにする（Workspace 限定の分岐は設けない）。

## 実装方式

- `mermaid` パッケージ（npm）をクライアントサイドで動的レンダリングする。
- ビルド時 SSR レンダリング（remark-mermaidjs + Puppeteer 等）は採用しない。既存の軽量な react-markdown 構成と相性が悪く、依存が重くなるため。

## 構成要素

### 1. 依存追加
- `apps/web/package.json` に `mermaid` を追加する。

### 2. `apps/web/components/ui/MermaidBlock.tsx`（新規）
- Props: `code: string`（mermaid記法のソース文字列）
- `mermaid` を動的 `import()` し、`useEffect` 内で一意な id を採番して `mermaid.render(id, code)` を呼び出す。
- 成功時: 返却された SVG 文字列を `dangerouslySetInnerHTML` でコンテナに描画する。
- 失敗時（構文エラー）:
  - 赤系の警告スタイルでエラーメッセージ（mermaid が返す例外メッセージ）を表示する。
  - その下に `<details>`/`<summary>` で元の mermaid コードを折りたたみ表示し、開けば確認できるようにする（デバッグ用途）。
- レンダリングは `code` の内容が変わったときのみ再実行する（`useEffect` の依存配列に `code` を指定）。

### 3. `MarkdownView.tsx` の変更
- `makeMarkdownComponents` の返り値に `code` コンポーネントを追加する。
- `className`（react-markdown が付与する `language-xxx` 形式）が `language-mermaid` のときのみ、`children` の文字列を `MermaidBlock` に渡してレンダリングを委譲する。
- それ以外の言語・インラインコードは既存どおり react-markdown のデフォルト `<code>` 表示のまま変更しない（明示的なオーバーライドを追加しないことで挙動を維持）。

### 4. サニタイズとの整合性
- `rehypeSanitize`(`sanitizeSchema`, `lib/briefing-toc.ts`) は `defaultSchema` をベースにしており、`code` 要素の `className`（`language-*` 形式）は標準で許可される。mermaid ブロック検出に必要な `language-mermaid` クラスはサニタイズ後も保持されるため、スキーマ変更は不要。
- mermaid が生成する SVG 自体は react-markdown/rehype のパイプラインを通さず、`MermaidBlock` 内で React が直接描画するため sanitize の対象外となる。

## テスト方針

- `MermaidBlock` の単体テスト（Vitest + Testing Library）: 正常な mermaid コードで SVG が描画されること、不正な構文でエラーメッセージと折りたたみコードが表示されることを確認する。
- `MarkdownView` の既存テストに、```mermaid フェンスを含む markdown を渡して `MermaidBlock` に処理が委譲されることを確認するケースを追加する。
- 手動確認: Workspace 画面で `articles/article11_rag.md`（スクリーンショットの対象ファイル）を開き、mermaid 図が実際にレンダリングされることをブラウザで確認する。

## スコープ外

- ダークモード時の mermaid テーマ切り替えの精緻な調整（既存の `prose dark:prose-invert` との統合含む）は本設計では最小限（mermaid のデフォルトテーマをそのまま使う）とし、必要であれば別途対応する。
- mermaid 以外の図表記法（PlantUML等）への対応は行わない。
