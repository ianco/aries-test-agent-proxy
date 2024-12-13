import { Inject } from '@tsed/di'
import { TestHarnessConfig } from './TestHarnessConfig'

export abstract class BaseController {
  @Inject()
  protected testHarnessConfig!: TestHarnessConfig

  protected get agent() {
    return this.testHarnessConfig.agent
  }

  public onStartup(): Promise<void> | void {}
}
