import { Controller, Get } from '@tsed/common'
import { BaseController } from '../BaseController'
import { TestHarnessConfig } from '../TestHarnessConfig'
import { CredoError } from '@credo-ts/core'

@Controller('/agent/command/did')
export class DidController extends BaseController {
  public constructor(testHarnessConfig: TestHarnessConfig) {
    super(testHarnessConfig)
  }

  @Get()
  async getPublicDid() {
    //const publicDidInfoRecord = await this.agent.genericRecords.findById('_INFO')
    const publicDidInfoRecord = await this.agent.genericRecords.findById('PUBLIC_DID_INFO')

    if (!publicDidInfoRecord) {
      throw new CredoError('Public DID Info Record not found')
    }

    //return publicDidInfoRecord ? publicDidInfoRecord.content.didInfo : {}
    //return (publicDidInfoRecord.content as { 'did-info': { did: string } })['did-info'].did
    const content = publicDidInfoRecord.content as { didInfo: { did: string } }
    const did = 'did:indy:bcovrin:test:' + content.didInfo.did
    //return content.didInfo.did
    return did
  }
}