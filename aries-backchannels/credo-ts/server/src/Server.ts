import { Configuration, Inject, Injectable } from '@tsed/di'
import { PlatformApplication } from '@tsed/common'
import '@tsed/platform-express' // /!\ keep this import
import '@tsed/swagger' // import swagger Ts.ED module
import * as bodyParser from 'body-parser'
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export const rootDir = __dirname

@Configuration({
  rootDir,
  acceptMimes: ['application/json'],
  httpsPort: false,
  swagger: [
    {
      path: '/docs',
      specVersion: '3.0.3',
    },
  ],
  mount: {
    '/': [`${rootDir}/controllers/**/*.ts`],
  },
})
@Injectable()
export class Server {
  @Inject()
  app!: PlatformApplication

  @Configuration()
  settings!: Configuration

  $beforeRoutesInit() {
    this.app.use(bodyParser.json())

    return null
  }
}
