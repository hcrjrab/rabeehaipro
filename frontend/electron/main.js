const { app, BrowserWindow, ipcMain, shell, dialog, Tray, Menu, nativeImage } = require("electron");
const path = require("path");
const { spawn } = require("child_process");

let mainWindow = null;
let tray = null;
let serverProcess = null;
const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
  app.quit();
}

const DEV_URL = "http://localhost:3000";
const PORT = 3000;

function startServer() {
  if (app.isPackaged) {
    const serverPath = path.join(process.resourcesPath, "app", "node_modules", "next", "dist", "bin", "next");
    serverProcess = spawn(process.execPath, [serverPath, "start", "-p", String(PORT)], {
      cwd: app.isPackaged ? path.join(process.resourcesPath, "app") : __dirname,
      stdio: "pipe",
    });
  } else {
    serverProcess = spawn("npx", ["next", "dev", "-p", String(PORT)], {
      cwd: path.join(__dirname, ".."),
      stdio: "pipe",
      shell: true,
    });
  }

  return new Promise((resolve) => {
    const handler = (data) => {
      const text = data.toString();
      if (text.includes("Local:")) {
        resolve();
      }
    };
    serverProcess.stdout.on("data", handler);
    serverProcess.stderr.on("data", handler);
    setTimeout(() => resolve(), 8000);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: "Rabeeh AI",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    show: false,
    frame: process.platform === "darwin",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    backgroundColor: "#0a0a0a",
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("close", (event) => {
    if (tray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  const url = app.isPackaged ? `http://localhost:${PORT}` : DEV_URL;
  mainWindow.loadURL(url);
}

function createTray() {
  const iconSize = process.platform === "win32" ? 32 : 16;
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("Rabeeh AI");

  const contextMenu = Menu.buildFromTemplate([
    { label: "Show", click: () => mainWindow?.show() },
    { label: "Hide", click: () => mainWindow?.hide() },
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => mainWindow?.show());
}

function registerIPC() {
  ipcMain.handle("app:getVersion", () => app.getVersion());
  ipcMain.handle("app:getPlatform", () => process.platform);

  ipcMain.handle("shell:openExternal", (_event, url) => {
    return shell.openExternal(url);
  });

  ipcMain.handle("dialog:openFile", async (_event, options) => {
    const result = await dialog.showOpenDialog(mainWindow, options);
    return result;
  });

  ipcMain.handle("dialog:saveFile", async (_event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result;
  });

  ipcMain.handle("window:minimize", () => mainWindow?.minimize());
  ipcMain.handle("window:maximize", () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow?.maximize();
    }
  });
  ipcMain.handle("window:close", () => mainWindow?.close());
  ipcMain.handle("window:isMaximized", () => mainWindow?.isMaximized());
}

app.whenReady().then(async () => {
  registerIPC();

  if (!app.isPackaged) {
    await startServer();
  }

  createWindow();
  createTray();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  tray?.destroy();
  tray = null;
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
});

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});
