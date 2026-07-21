# mermaid 図のモーダル拡大表示 設計

## 背景・目的

Workspace の Markdown プレビューで mermaid 図をレンダリングできるようになった（`MermaidBlock`）。次のステップとして、GitHub の画像プレビューのように、レンダリングされた図をクリックするとモーダルで拡大表示し、ズーム・パン操作ができるようにする。

## 適用範囲

`MermaidBlock` が描画する SVG のみを対象とする。Markdown 内の通常の画像（`![alt](src)`）は対象外。

## トリガーとモーダルUI

- 図（SVG）を直接クリックするとモーダルが開く。追加の拡大アイコン等は表示しない。
- モーダルは全画面オーバーレイ + 中央にコンテンツ。閉じる手段は以下の3つ:
  - 右上の ✕ ボタン
  - ESC キー
  - オーバーレイ背景のクリック（コンテンツ領域自体のクリックは閉じない）
- モーダルを開いている間は背景のスクロールを止める（`document.body` の overflow 制御）。

## ズーム・パン操作

- ライブラリ `react-zoom-pan-pinch` を導入し、`TransformWrapper` / `TransformComponent` で SVG をラップする。
- 操作手段:
  - 右下（または画面端）に +/-/リセットの操作ボタンを配置する（スクリーンショットの GitHub モーダルに準拠したレイアウト）。
  - マウスドラッグによるパン操作。
  - マウスホイールでのズームは対象外（ボタン + ドラッグパンのみ）。

## 構成要素

### 1. 依存追加
- `apps/web/package.json` に `react-zoom-pan-pinch` を追加する。

### 2. `apps/web/components/ui/MermaidModal.tsx`（新規）
- Props: `{ svg: string; onClose: () => void }`
- オーバーレイ + `TransformWrapper`（`react-zoom-pan-pinch`）で `svg` を `dangerouslySetInnerHTML` 表示する。
- `TransformWrapper` の `wheel={{ disabled: true }}` を設定し、ホイールズームは無効化してドラッグパンとボタンズームのみ有効にする。
- `useControls()` フックで取得した `zoomIn` / `zoomOut` / `resetTransform` をボタンにバインドする。
- ESC キー押下で `onClose` を呼ぶ `useEffect` のキーリスナーを実装する。
- マウント時に `document.body.style.overflow = "hidden"`、アンマウント時に元に戻す。

### 3. `MermaidBlock.tsx` の変更
- 成功時（`state.status === "success"`）の SVG 表示 `<div dangerouslySetInnerHTML>` に `onClick` ハンドラと `cursor-zoom-in` 相当のスタイルを追加する。
- クリックで `isModalOpen` state を true にし、`isModalOpen` が true のとき `MermaidModal` を表示する（`state.svg` を渡す）。

## テスト方針

- `MermaidModal` の単体テスト: 開いた状態で ✕ ボタン・ESCキー・背景クリックそれぞれで `onClose` が呼ばれることを確認する。`react-zoom-pan-pinch` はモックせず実際の挙動を使い、ズームボタンクリックで内部 transform state が変化すること（`data-testid` 等で確認可能な範囲）を確認する。
- `MermaidBlock` の単体テスト: SVG 表示部分をクリックすると `MermaidModal` 相当の要素が表示されることを確認する（`MermaidModal` はモックしてよい）。
- 手動確認: Workspace 画面で mermaid 図を表示し、クリックでモーダルが開く・ズームイン/アウト/リセット・ドラッグパン・ESC/背景クリック/✕ボタンでの閉じる動作をブラウザで確認する。

## スコープ外

- Markdown 内の通常画像へのモーダル対応。
- マウスホイールズーム、ピンチズーム（タッチ操作）の明示的な作り込み（ライブラリのデフォルト任せにはしない — wheel は明示的に無効化する）。
