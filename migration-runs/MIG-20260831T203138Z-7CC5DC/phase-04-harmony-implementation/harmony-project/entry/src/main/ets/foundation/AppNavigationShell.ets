// Foundation (Phase 3 native UI base): ArkUI-native navigation routing shell.
//
// Pure shell, no business logic. Holds the single NavPathStack and the
// route registry. Phase 4 deterministically extends page-shell destinations
// from the Phase 3 route graph (route-registry.csv) and Behavior Contracts;
// hand-drawing a custom navigation stack is prohibited.
//
// Registered by nav-shell.capy-01: 7 Route-IDs from surface-plan.json routes.

import { ShellPageAddaccountscreenA9c749bc } from '../pages/shells/ShellPageAddaccountscreenA9c749bc';
import { ShellPageArticlescreen23af0624 } from '../pages/shells/ShellPageArticlescreen23af0624';
import { ShellPageImagepage18d3e5ad } from '../pages/shells/ShellPageImagepage18d3e5ad';
import { ShellPageLoginscreen9d67f9d2 } from '../pages/shells/ShellPageLoginscreen9d67f9d2';
import { ShellPageMainactivity3fde9431 } from '../pages/shells/ShellPageMainactivity3fde9431';
import { ShellPageOpenarticleinbrowseractivityD9097de2 } from '../pages/shells/ShellPageOpenarticleinbrowseractivityD9097de2';
import { ShellPageSettingsscreenD0a9ff8d } from '../pages/shells/ShellPageSettingsscreenD0a9ff8d';
import { ArticleReaderPage } from '../pages/reader/ArticleReaderPage';

export interface FoundationRouteEntry {
  routeId: string;
  title: string;
}

// Route registry (deterministic, from Phase 3 route-registry.csv; contract-only).
const ROUTE_REGISTRY: FoundationRouteEntry[] = [
  { routeId: 'PAGE-ADDACCOUNTSCREEN-A9C749BC', title: 'PAGE-ADDACCOUNTSCREEN-A9C749BC' },
  { routeId: 'PAGE-ARTICLESCREEN-23AF0624', title: 'PAGE-ARTICLESCREEN-23AF0624' },
  { routeId: 'PAGE-IMAGEPAGE-18D3E5AD', title: 'PAGE-IMAGEPAGE-18D3E5AD' },
  { routeId: 'PAGE-LOGINSCREEN-9D67F9D2', title: 'PAGE-LOGINSCREEN-9D67F9D2' },
  { routeId: 'PAGE-MAINACTIVITY-3FDE9431', title: 'PAGE-MAINACTIVITY-3FDE9431' },
  { routeId: 'PAGE-OPENARTICLEINBROWSERACTIVITY-D9097DE2', title: 'PAGE-OPENARTICLEINBROWSERACTIVITY-D9097DE2' },
  { routeId: 'PAGE-SETTINGSSCREEN-D0A9FF8D', title: 'PAGE-SETTINGSSCREEN-D0A9FF8D' }
];

@Component
export struct AppNavigationShell {
  @Provide('foundationPathStack') pathStack: NavPathStack = new NavPathStack();
  // Route registry: one entry per Route-ID (route-registry.csv).
  @State routeRegistry: FoundationRouteEntry[] = ROUTE_REGISTRY;
  @BuilderParam homeContent: () => void = this.defaultHomeContent;
  // Minimum route-opening behavior required by ROUTE_SMOKE (no business logic).
  @Prop initialRoute: string = '';

  @Builder
  defaultHomeContent() {
    Column() {}
      .id('AppNavigationShellHome')
      .width('100%')
      .height('100%')
  }

  // Destination builder: maps a registered route name to its page shell
  // (deterministic mapping, one branch per Route-ID).
  @Builder
  pageMap(name: string, param?: object) {
    if (name === 'PAGE-ADDACCOUNTSCREEN-A9C749BC') {
      ShellPageAddaccountscreenA9c749bc()
    } else 
    if (name === 'PAGE-ARTICLESCREEN-23AF0624') {
      ShellPageArticlescreen23af0624()
    } else 
    if (name === 'PAGE-IMAGEPAGE-18D3E5AD') {
      ShellPageImagepage18d3e5ad()
    } else 
    if (name === 'PAGE-LOGINSCREEN-9D67F9D2') {
      ShellPageLoginscreen9d67f9d2()
    } else 
    if (name === 'PAGE-MAINACTIVITY-3FDE9431') {
      ShellPageMainactivity3fde9431()
    } else 
    if (name === 'PAGE-OPENARTICLEINBROWSERACTIVITY-D9097DE2') {
      ShellPageOpenarticleinbrowseractivityD9097de2()
    } else
    if (name === 'PAGE-ARTICLEREADER-B2B865F0') {
      ArticleReaderPage()
    } else 
    if (name === 'PAGE-SETTINGSSCREEN-D0A9FF8D') {
      ShellPageSettingsscreenD0a9ff8d()
    } else {
      Column() {}
        .id(name)
        .width('100%')
        .height('100%')
    }
  }

  build() {
    Navigation(this.pathStack) {
      this.homeContent()
    }
    .navDestination(this.pageMap)
    .hideTitleBar(true)
    .mode(NavigationMode.Stack)
    .id('AppNavigationShell')
    .width('100%')
    .height('100%')
    .onAppear((): void => {
      if (this.initialRoute !== '' && this.pathStack.size() === 0) {
        this.pathStack.pushPathByName(this.initialRoute, undefined);
      }
    })
  }
}
