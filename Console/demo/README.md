# YMOS Console 浏览器 Demo

这里保存静态 Reader 模板；其余页面由 `scripts/build_console_demo.py` 从正式 Console 源文件生成。

```bash
python3 scripts/build_console_demo.py --output _site
python3 -m http.server 8000 --directory _site
```

浏览器 Demo 与正式 Console 的边界：

- 只包含三份带 `ymos_sample: true` 和 `synthetic: true` 的合成报告；
- 不运行 Python 后端，不读写用户 vault，不执行交易；
- 草稿和演示账户参数只保存在当前浏览器的 `localStorage`；
- 正式页面保持不变，仍以服务端 Markdown 作为真相源；
- 构建脚本找不到预期适配点时会失败，避免 Console 更新后发布行为不确定的旧 Demo。

`_site/` 是临时构建产物，不提交到 Git；GitHub Actions 会直接把它作为 Pages artifact 发布。
