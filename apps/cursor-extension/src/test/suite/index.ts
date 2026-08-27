import * as path from "node:path";

import Mocha from "mocha";

export function run(): Promise<void> {
  const mocha = new Mocha({
    ui: "tdd",
    color: true,
    timeout: 30_000,
  });
  mocha.addFile(path.resolve(__dirname, "extension.smoke.test.js"));
  return new Promise((resolve, reject) => {
    mocha.run((failures) => {
      if (failures > 0) {
        reject(new Error(`${failures} Extension Host tests failed`));
        return;
      }
      resolve();
    });
  });
}
