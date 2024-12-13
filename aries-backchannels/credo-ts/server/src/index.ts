import { $log, registerProvider, InjectorService } from '@tsed/common'
import minimist from 'minimist'
import { PlatformExpress } from '@tsed/platform-express'
import { Server } from './Server'
import { TestHarnessConfig } from './TestHarnessConfig'

async function startup() {
  const cliArguments = minimist(process.argv.slice(2), {
    alias: {
      port: 'p',
    },
    default: {
      port: 9020,
    },
  })

  const testHarnessConfig = new TestHarnessConfig({ backchannelPort: Number(cliArguments.port) })

  registerProvider({
    provide: TestHarnessConfig,
    useValue: testHarnessConfig,
  })

  $log.level = 'debug'

  // TODO: Set up native logger for anoncreds, askar and indy-vdr

  await testHarnessConfig.startAgent({ inboundTransports: ['http'], outboundTransports: ['http'] })

  try {
    $log.debug('Start server...')

    const platform = await PlatformExpress.bootstrap(Server, {
      httpPort: testHarnessConfig.backchannelPort,
    })

    const injector = platform.injector as InjectorService
    injector.addProvider(TestHarnessConfig, { useValue: testHarnessConfig })

    await testHarnessConfig.agentStartup()

    await platform.listen(true)

    $log.level = 'debug'
  } catch (er) {
    $log.error(er)

    throw er
  }
}

startup()
