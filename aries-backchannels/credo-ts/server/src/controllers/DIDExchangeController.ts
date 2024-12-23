import { Controller, Get, PathParams, Post, BodyParams } from '@tsed/common'
import { NotFound } from '@tsed/exceptions'
import {
  OutOfBandRecord,
  OutOfBandInvitation,
  ConnectionInvitationMessage,
  ConnectionRecord,
  JsonTransformer,
  AgentConfig,
  OutOfBandEventTypes,
  OutOfBandStateChangedEvent,
  OutOfBandState,
  CredoError,
  DidExchangeState,
  ReceiveOutOfBandImplicitInvitationConfig,
} from '@credo-ts/core'

import { filter, firstValueFrom, ReplaySubject, tap, timeout } from 'rxjs'
import { BaseController } from '../BaseController'
import { TestHarnessConfig } from '../TestHarnessConfig'
import { ConnectionUtils } from '../utils/ConnectionUtils'

@Controller('/agent/command/did-exchange')
export class DIDExchangeController extends BaseController {
  private subject = new ReplaySubject<OutOfBandStateChangedEvent>()

  public constructor(testHarnessConfig: TestHarnessConfig) {
    super(testHarnessConfig)
  }

  onStartup = () => {
    this.subject = new ReplaySubject<OutOfBandStateChangedEvent>()
    // Catch all events in replay subject for later use
    this.agent.events
      .observable<OutOfBandStateChangedEvent>(OutOfBandEventTypes.OutOfBandStateChanged)
      .subscribe(this.subject)
  }

  @Get('/:id')
  async getConnectionById(@PathParams('id') id: string) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    if (!connection) throw new NotFound(`Connection with id ${id} not found`)

    return connection
  }

  @Post('/create-request-resolvable-did')
  async createRequestResolvableDID(@BodyParams() data: { data: { their_public_did: string } }) {
    const { their_public_did } = data.data;

    const { outOfBandRecord, connectionRecord } = await this.agent.oob.receiveImplicitInvitation({ did: their_public_did } as ReceiveOutOfBandImplicitInvitationConfig);

    // Add the two records to the response and move the state from the connectionRecord to the root of connectionRecords.
    const connectionRecords = {
      ...(connectionRecord && { connectionRecord }),
      ...(outOfBandRecord && { outOfBandRecord }),
      ...(connectionRecord && { state: connectionRecord.state }),
      ...(connectionRecord && { connection_id: connectionRecord.outOfBandId })
    }

    return connectionRecords
  }

  // Implementing this method just to satisfy AATH. This will not call credo and just set the state that was set in the previous step of receive invitation.
  @Post('/send-request')
  async sendRequest(@BodyParams('id') id: string) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)
    
    if (!connection) {
      throw new CredoError('Connection not found')
    }

    //connection.state = DidExchangeState.RequestSent

    return connection
  }

  // Implementing this method just to satisfy AATH. This will not call credo and just set the state that was set in the previous step of receive invitation.
  @Post('/send-response')
  //async sendResponse(@BodyParams('id') id: string) {
  //async sendResponse(@PathParams('id') id: string, @BodyParams('mediator_connection_id') mediatorConnectionId: string) {
  async sendResponse(@BodyParams('id') id: string, @BodyParams('mediator_connection_id') mediatorConnectionId: string) {
    //const { mediator_connection_id, ...invitationJson } = data

    // If we have a mediator connection id, we need to find the mediator id
    if (mediatorConnectionId) {
      const id = await this.mediatorIdFromMediatorConnectionId(mediatorConnectionId)
    }

    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    return connection
  }

  private async mediatorIdFromMediatorConnectionId(mediatorConnectionId?: string): Promise<string | undefined> {
    if (!mediatorConnectionId) return undefined

    // Find mediator id if mediator connection id is provided
    const mediator = await this.agent.mediationRecipient.findByConnectionId(mediatorConnectionId)

    return mediator?.id
  }
}

@Controller('/agent/response/did-exchange')
export class DIDExchangeResponseController extends BaseController {
  public constructor(testHarnessConfig: TestHarnessConfig) {
    super(testHarnessConfig)
  }

  @Get('/:id')
  async getDidExchangeResponse(@PathParams('id') id: string) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    if (!connection) throw new NotFound(`Connection with id ${id} not found`)

    return connection
  }
}