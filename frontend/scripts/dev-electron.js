const { spawn } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");

const nextProcess = spawn("npx", ["next", "dev", "-p", "3000"], {
  cwd: root,
  stdio: "pipe",
  shell: true,
});

let electronStarted = false;

function tryStartElectron(data) {
  const text = data.toString();
  if (text.includes("Local:") && !electronStarted) {
    electronStarted = true;
    const electronProcess = spawn(
      path.join(root, "node_modules", ".bin", "electron"),
      ["."],
      { cwd: root, stdio: "inherit", shell: true }
    );
    electronProcess.on("close", () => {
      nextProcess.kill();
      process.exit();
    });
  }
}

nextProcess.stdout.on("data", (data) => {
  process.stdout.write(data);
  tryStartElectron(data);
});

nextProcess.stderr.on("data", (data) => {
  process.stderr.write(data);
  tryStartElectron(data);
});

process.on("SIGINT", () => {
  nextProcess.kill();
  process.exit();
});
