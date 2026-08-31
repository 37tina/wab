// DebugSemanticProbe - semantic data snapshot probe (batch 2 #85).
// HASH-FROZEN after Phase 3: Phase 4 implementers must NOT modify
// this file (work order carries the expected sha256; Gate 4 checks).
// Wire real providers from your own files via SemanticProbeRegistry
// .registerProbe(key, provider) instead.
//
// Channels: A) sandbox file files/semantic-probe.json
//           B) hilog tag 'SemanticProbe' SNAPSHOT lines
import fs from '@ohos.file.fs';
import hilog from '@ohos.hilog';
import { collectProbeSnapshot } from './SemanticProbeRegistry';

const TAG = 'SemanticProbe';
const INTERVAL_MS = 2000;
let timerId: number = -1;

function snapshotJson(): string {
  const snapshot = collectProbeSnapshot();
  return JSON.stringify(snapshot);
}

export function startSemanticProbe(filesDir: string): void {
  if (timerId >= 0) {
    return;
  }
  const target = filesDir + '/semantic-probe.json';
  timerId = setInterval(() => {
    const json = snapshotJson();
    hilog.info(0x0000, TAG, 'SNAPSHOT %{public}s', json);
    try {
      const exists = fs.accessSync(target);
      const file = fs.openSync(
        target,
        fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE
          | (exists ? fs.OpenMode.TRUNC : 0));
      fs.writeSync(file.fd, json);
      fs.closeSync(file);
    } catch (e) {
      hilog.error(0x0000, TAG, 'snapshot write failed: %{public}s',
        JSON.stringify(e));
    }
  }, INTERVAL_MS);
}
