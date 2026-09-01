import { startSemanticProbe } from '../probe/DebugSemanticProbe';
import { AbilityConstant, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';

const DOMAIN = 0x0000;

export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    // batch-2 #85: frozen semantic probe autostart
    startSemanticProbe(this.context.filesDir);

    // Minimum route-opening behavior for ROUTE_SMOKE (nav-shell.capy-01):
    // an aa-start want parameter 'routeName' selects the page-shell route
    // opened at launch. Contract-only navigation affordance; no business
    // logic. Absent parameter keeps the frozen home route.
    const smokeRoute = want?.parameters?.['routeName'];
    if (typeof smokeRoute === 'string' && smokeRoute !== '') {
      AppStorage.setOrCreate('smokeRouteName', smokeRoute);
    }

    try {
      this.context.getApplicationContext().setColorMode(ConfigurationConstant.ColorMode.COLOR_MODE_NOT_SET);
    } catch (err) {
      hilog.error(DOMAIN, 'CAPYREADER', 'Failed to set colorMode. Cause: %{public}s', JSON.stringify(err));
    }
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onCreate');
  }

  onDestroy(): void {
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onDestroy');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    // Main window is created, set main page for this ability
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onWindowStageCreate');

    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        hilog.error(DOMAIN, 'CAPYREADER', 'Failed to load the content. Cause: %{public}s', JSON.stringify(err));
        return;
      }
      hilog.info(DOMAIN, 'CAPYREADER', 'Succeeded in loading the content.');
    });
  }

  onWindowStageDestroy(): void {
    // Main window is destroyed, release UI related resources
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onWindowStageDestroy');
  }

  onForeground(): void {
    // Ability has brought to foreground
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onForeground');
  }

  onBackground(): void {
    // Ability has back to background
    hilog.info(DOMAIN, 'CAPYREADER', '%{public}s', 'Ability onBackground');
  }
}
