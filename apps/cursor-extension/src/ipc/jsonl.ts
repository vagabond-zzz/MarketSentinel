export class JsonlDecoder {
  private buffer = "";

  push(chunk: string | Buffer): string[] {
    this.buffer += typeof chunk === "string" ? chunk : chunk.toString("utf8");
    const lines: string[] = [];
    for (;;) {
      const newline = this.buffer.indexOf("\n");
      if (newline < 0) {
        return lines;
      }
      let line = this.buffer.slice(0, newline);
      this.buffer = this.buffer.slice(newline + 1);
      if (line.endsWith("\r")) {
        line = line.slice(0, -1);
      }
      if (line.trim() === "") {
        continue;
      }
      lines.push(line);
    }
  }
}
