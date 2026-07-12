import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter"
import bash from "react-syntax-highlighter/dist/cjs/languages/prism/bash"
import css from "react-syntax-highlighter/dist/cjs/languages/prism/css"
import go from "react-syntax-highlighter/dist/cjs/languages/prism/go"
import java from "react-syntax-highlighter/dist/cjs/languages/prism/java"
import javascript from "react-syntax-highlighter/dist/cjs/languages/prism/javascript"
import json from "react-syntax-highlighter/dist/cjs/languages/prism/json"
import jsx from "react-syntax-highlighter/dist/cjs/languages/prism/jsx"
import markup from "react-syntax-highlighter/dist/cjs/languages/prism/markup"
import php from "react-syntax-highlighter/dist/cjs/languages/prism/php"
import python from "react-syntax-highlighter/dist/cjs/languages/prism/python"
import ruby from "react-syntax-highlighter/dist/cjs/languages/prism/ruby"
import rust from "react-syntax-highlighter/dist/cjs/languages/prism/rust"
import scss from "react-syntax-highlighter/dist/cjs/languages/prism/scss"
import sql from "react-syntax-highlighter/dist/cjs/languages/prism/sql"
import toml from "react-syntax-highlighter/dist/cjs/languages/prism/toml"
import tsx from "react-syntax-highlighter/dist/cjs/languages/prism/tsx"
import typescript from "react-syntax-highlighter/dist/cjs/languages/prism/typescript"
import yaml from "react-syntax-highlighter/dist/cjs/languages/prism/yaml"
import { oneDark } from "react-syntax-highlighter/dist/cjs/styles/prism"

// Register only the languages we map in lib/fileColors.ts (languageForFile),
// so the preview highlights match the same extension set as the icon colors.
SyntaxHighlighter.registerLanguage("python", python)
SyntaxHighlighter.registerLanguage("javascript", javascript)
SyntaxHighlighter.registerLanguage("jsx", jsx)
SyntaxHighlighter.registerLanguage("typescript", typescript)
SyntaxHighlighter.registerLanguage("tsx", tsx)
SyntaxHighlighter.registerLanguage("json", json)
SyntaxHighlighter.registerLanguage("markup", markup)
SyntaxHighlighter.registerLanguage("css", css)
SyntaxHighlighter.registerLanguage("scss", scss)
SyntaxHighlighter.registerLanguage("yaml", yaml)
SyntaxHighlighter.registerLanguage("toml", toml)
SyntaxHighlighter.registerLanguage("bash", bash)
SyntaxHighlighter.registerLanguage("rust", rust)
SyntaxHighlighter.registerLanguage("go", go)
SyntaxHighlighter.registerLanguage("java", java)
SyntaxHighlighter.registerLanguage("ruby", ruby)
SyntaxHighlighter.registerLanguage("php", php)
SyntaxHighlighter.registerLanguage("sql", sql)

export function CodeView({ content, language }: { content: string; language: string }) {
  return (
    <SyntaxHighlighter
      language={language}
      style={oneDark}
      customStyle={{ margin: 0, background: "transparent", fontSize: "0.8125rem" }}
      showLineNumbers
      data-testid="code-view"
    >
      {content}
    </SyntaxHighlighter>
  )
}
