// With nodeIntegration enabled, preload just sets up IPC convenience functions
// on window.cc for the renderer to use.

const { ipcRenderer } = require('electron');

window.cc = {
  // PTY operations
  createPty: (slot, sessionName) => ipcRenderer.invoke('pty:create', slot, sessionName),
  writePty: (slot, data) => ipcRenderer.send('pty:write', slot, data),
  resizePty: (slot, cols, rows) => ipcRenderer.send('pty:resize', slot, cols, rows),
  scrollTmux: (slot, direction) => ipcRenderer.send('pty:scroll', slot, direction),
  exitCopyMode: (slot) => ipcRenderer.send('pty:exit-copy-mode', slot),
  killPty: (slot) => ipcRenderer.invoke('pty:kill', slot),
  newClaude: (slot) => ipcRenderer.invoke('pty:new-claude', slot),

  // PTY events (remove old listeners first to prevent duplicates on reload)
  onPtyData: (callback) => {
    ipcRenderer.removeAllListeners('pty:data');
    ipcRenderer.on('pty:data', (_, slot, data) => callback(slot, data));
  },
  onPtyExit: (callback) => {
    ipcRenderer.removeAllListeners('pty:exit');
    ipcRenderer.on('pty:exit', (_, slot, exitCode) => callback(slot, exitCode));
  },

  // Context menu
  showContextMenu: (sessionName, displayName) => {
    ipcRenderer.send('context-menu', sessionName, displayName);
  },

  // Actions from main process (remove old listeners first to prevent duplicates on reload)
  onAssignSlot: (callback) => {
    ipcRenderer.removeAllListeners('assign-slot');
    ipcRenderer.on('assign-slot', (_, slot, sessionName) => callback(slot, sessionName));
  },
  onAction: (callback) => {
    ipcRenderer.removeAllListeners('action');
    ipcRenderer.on('action', (_, action, sessionName, extra) => callback(action, sessionName, extra));
  },
};
