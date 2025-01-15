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
  CreateOutOfBandInvitationConfig,
} from '@credo-ts/core'

import { convertToNewInvitation } from '@credo-ts/core/build/modules/oob/helpers'
import { convertToOldInvitation } from '@credo-ts/core/build/modules/oob/helpers'
import { ProofUtils } from '../utils/ProofUtils'
import { CredentialUtils } from '../utils/CredentialUtils'
import { filter, firstValueFrom, ReplaySubject, tap, timeout } from 'rxjs'
import { BaseController } from '../BaseController'
import { TestHarnessConfig } from '../TestHarnessConfig'
import { ConnectionUtils } from '../utils/ConnectionUtils'
import { DidController } from './DidController';

@Controller('/agent/command/out-of-band')
export class OutOfBandController extends BaseController {
  private subject = new ReplaySubject<OutOfBandStateChangedEvent>()
  private didController: DidController;

  public constructor(testHarnessConfig: TestHarnessConfig, didController: DidController) {
    super(testHarnessConfig);
    this.didController = didController;
  }

  onStartup = () => {
    this.subject = new ReplaySubject<OutOfBandStateChangedEvent>()
    // Catch all events in replay subject for later use
    this.agent.events
      .observable<OutOfBandStateChangedEvent>(OutOfBandEventTypes.OutOfBandStateChanged)
      .subscribe(this.subject)
  }

  // Define the state translation dictionary
  didExchangeResponderStateTranslationDict: { [key: string]: string } = {
    "Initial": "invitation-sent",
    "invitation": "invitation-sent",
    "request": "request-received",
    "response": "response-sent",
    "?": "abandoned",
    "active": "completed",
    "completed": "completed",
  };

  @Get('/:id')
  async getConnectionById(@PathParams('id') id: string) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    if (!connection) throw new NotFound(`Connection with id ${id} not found`)

    return this.mapConnection(connection)
  }

  @Get('/')
  async getAllConnections() {
    const connections = await this.agent.connections.getAll()

    return connections.map((conn) => this.mapConnection(conn))
  }

  @Post('/create-invitation')
  async createInvitation(@BodyParams('data') data?: { mediator_connection_id?: string, [key: string]: any }) {
    const mediatorId = await this.mediatorIdFromMediatorConnectionId(data?.mediator_connection_id)

    // Adjust the invitation details based on it's contents
    const invitationOptions = await this.mapOOBInvitationDetails(data)

    if (!invitationOptions.invitationDid) {
      // If there is no public did in the invitation then we can use routing.
      const routing = await this.agent.mediationRecipient.getRouting({
        mediatorId,
      })
      invitationOptions.routing = routing
    }
    else {
      // Remove routing from invitationOptions if it exists
      delete invitationOptions.routing
    }

    // let invitationOptions: any = {
    //   autoAcceptConnection: true,
    //   ...data, // Spread the entire data object into invitationOptions
    // };

    // If data contains use_public_did call DidController.getPublicDid() to get the public DID
    // if (data?.use_public_did) {
    //   const publicDid = await this.didController.getPublicDid();
    //   if (publicDid) {
    //     invitationOptions.invitationDid = publicDid;
    //   }
    // }

    // Remove all undefined values from invitationOptions
    Object.keys(invitationOptions).forEach(key => (invitationOptions as any)[key] === undefined && delete (invitationOptions as any)[key]);
    

    const outOfBandRecord = await this.agent.oob.createInvitation(invitationOptions)

    const config = this.agent.dependencyManager.resolve(AgentConfig)
    const invitation = outOfBandRecord.outOfBandInvitation
    const invitationJson = invitation.toJSON({ useDidSovPrefixWhereAllowed: config.useDidSovPrefixWhereAllowed })

    return {
      //state: OutOfBandState.Initial,
      state: DidExchangeState.InvitationSent,
      // This should be the connection id. However, the connection id is not available until a request is received.
      // We can just use the oob invitation I guess.
      connection_id: outOfBandRecord.id,
      invitation: invitationJson,
      originalCredoState: OutOfBandState.Initial,
    }
  }

  @Post('/send-invitation-message')
  async sendInvitationMessage(@BodyParams() { data }: { data: any }) {
    // Implement the logic to send an invitation message

    // Create the invitation
    const invitation = await this.createInvitation(data);
    // Translate the state in the invitation to what the test harness expects.
    //invitation.state = this.didExchangeResponderStateTranslationDict[invitation.state] as OutOfBandState || invitation.state;
    
    //const result = await this.agent.sendInvitationMessage(invitationDetails)
    return invitation
  }

  @Post('/receive-invitation')
  async receiveInvitation(@BodyParams('data') data: Record<string, unknown> & { mediator_connection_id?: string }) {
    const { mediator_connection_id, ...invitationJson } = data as any

    const mediatorId = await this.mediatorIdFromMediatorConnectionId(mediator_connection_id)

    const routing = await this.agent.mediationRecipient.getRouting({
      mediatorId,
    })

    this.agent.config.logger.debug('invitationJson: ', invitationJson)
    const oobInvitation = JsonTransformer.fromJSON(invitationJson, OutOfBandInvitation)

    const { outOfBandRecord, connectionRecord } = await this.agent.oob.receiveInvitation(oobInvitation, {
      routing,
      autoAcceptConnection: true, //was false
      autoAcceptInvitation: true,
    })

    this.agent.config.logger.debug('OutOfBandController.receiveInvitation: outOfBandRecord: ', outOfBandRecord)
    this.agent.config.logger.debug('OutOfBandController.receiveInvitation: connectionRecord: ', connectionRecord)

    // if (!outOfBandRecord) {
    //   throw new CredoError('Processing invitation did not result in a out of band record')
    // }

    if (!connectionRecord) {
      throw new CredoError('Processing invitation did not result in a connection record')
    }

    // Credo doesn't support the send-request message. It does this at this point of accepting the invitation.
    // Therefore the state at this point in the protocol is request-sent. 
    // Set the state to invitation-received at the route of the response. This is the state that the test harness expects at this point.
    // The send-request message will just bypass any calls to Credo and set the state to request-sent.
    //connectionRecord.originalCredoState = connectionRecord.state
    if (connectionRecord.state === DidExchangeState.RequestSent) {
      connectionRecord.state = DidExchangeState.InvitationReceived
    }

    // Add the two records to the response and move the state from the connectionRecord to the root of connectionRecords.
    const connectionRecords = {
      ...(connectionRecord && { connectionRecord }),
      ...(outOfBandRecord && { outOfBandRecord }),
      ...(connectionRecord && { state: connectionRecord.state }),
      ...(connectionRecord && { connection_id: connectionRecord.outOfBandId })
    }

    //return this.mapConnection(connectionRecord)
    //return connectionRecord
    //return outOfBandRecord
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

    return this.mapConnection(connection)
  }

  @Post('/accept-invitation')
  async acceptInvitation(@BodyParams('id') id: string) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    return this.mapConnection(connection)
  }

  @Post('/accept-request')
  async acceptRequest(@BodyParams('id') id: string) {
    // possible here that the request hasn't finished processing yet
    //await this.waitForState(id, DidExchangeState.RequestReceived)

    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    return this.mapConnection(connection)
  }

  @Post('/send-ping')
  async sendPing(
    @BodyParams('id') id: string,
    // For now we ignore data. This could contain a comment property,
    // AFJ doesn't support passing it for now
    @BodyParams('data') data: any
  ) {
    const connection = await ConnectionUtils.getConnectionByConnectionIdOrOutOfBandId(this.agent, id)

    if (!connection) throw new NotFound(`Connection with id ${id} not found`)

    return this.mapConnection(connection)
  }

  private async mediatorIdFromMediatorConnectionId(mediatorConnectionId?: string): Promise<string | undefined> {
    if (!mediatorConnectionId) return undefined

    // Find mediator id if mediator connection id is provided
    const mediator = await this.agent.mediationRecipient.findByConnectionId(mediatorConnectionId)

    return mediator?.id
  }

  // private async waitForState(id: string, state: DidExchangeState) {
  //   return await firstValueFrom(
  //     this.subject.pipe(
  //       filter((c) => c.payload.connectionRecord.id === id ),
  //       filter((c) => c.payload.connectionRecord.state === state),
  //       timeout(20000)
  //     )
  //   )
  // }

  private mapConnection(connection: ConnectionRecord) {
    return {
      // If we use auto accept, we can't include the state as we will move quicker than the calls in the test harness. This will
      // make verification fail. The test harness recognizes the 'N/A' state for some connection types.
      state: connection.state === DidExchangeState.Completed ? connection.rfc0160State : 'N/A',
      connection_id: connection.id,
      connection,
    }
  }


  private async mapOOBInvitationDetails(details: any): Promise<CreateOutOfBandInvitationConfig> {
    const invitationOptions: CreateOutOfBandInvitationConfig = {
      label: details.label,
      alias: details.alias,
      imageUrl: details.imageUrl,
      goalCode: details.goalCode,
      goal: details.goal,
      handshake: details.handshake || true,
      handshakeProtocols: details.handshakeProtocols,
      messages: details.messages,
      multiUseInvitation: details.multiUseInvitation || false,
      autoAcceptConnection: details.autoAcceptConnection || true,
      routing: details.routing,
      appendedAttachments: details.appendedAttachments,
    };
  
    if (details.use_public_did === true) {
      const publicDid = await this.didController.getPublicDid();
      if (publicDid) {
        invitationOptions.invitationDid = publicDid as string;
      }
    }

    return invitationOptions;
  }


  private async oldmapOOBInvitationDetails(invitationDetails: any) {
    // Adjust the invitation details based on it's contents

    // export interface CreateOutOfBandInvitationConfig {
    //   label?: string;
    //   alias?: string;
    //   imageUrl?: string;
    //   goalCode?: string;
    //   goal?: string;
    //   handshake?: boolean;
    //   handshakeProtocols?: HandshakeProtocol[];
    //   messages?: AgentMessage[];
    //   multiUseInvitation?: boolean;
    //   autoAcceptConnection?: boolean;
    //   routing?: Routing;
    //   appendedAttachments?: Attachment[];
    //   /**
    //    * Did to use in the invitation. Cannot be used in combination with `routing`.
    //    */
    //   invitationDid?: string;

    const auto_accept = "false";
    const multi_use = "false";
    let agent_operation = "create-invitation?multi_use=" + multi_use;

    const attachments = invitationDetails.attachments || [];
    const handshake_protocols = invitationDetails.handshake_protocols || null;
    const formatted_attachments: any[] = [];
    const use_did_method = invitationDetails.use_did_method || null;
    const use_did = invitationDetails.use_did || null;

    for (const attachment of attachments) {
      const message_type = attachment["@type"];
      const thread_id = attachment["~thread"]?.thid || attachment["@id"];
      let record_id, record_type;

      if (message_type.endsWith("/issue-credential/1.0/offer-credential")) {
        const credential = await CredentialUtils.getCredentialByThreadId(this.agent, thread_id)
        //const resp = await this.admin_GET("/issue-credential/records", { params: { thread_id } });
        //const resp_json = await resp.json();
        //record_id = resp_json.results[0].credential_exchange_id;
        record_type = "credential-offer";
      // } else if (message_type.endsWith("/issue-credential/2.0/offer-credential")) {
      //   const resp = await this.admin_GET("/issue-credential-2.0/records", { params: { thread_id } });
      //   const resp_json = await resp.json();
      //   record_id = resp_json.results[0].cred_ex_record.cred_ex_id;
      //   record_type = "credential-offer";
      } else if (message_type.endsWith("present-proof/1.0/request-presentation")) {
        const proof = await ProofUtils.getProofByThreadId(this.agent, thread_id)
        //const resp = await this.admin_GET("/present-proof/records", { params: { thread_id } });
        //const resp_json = await resp.json();
        //record_id = resp_json.results[0].presentation_exchange_id;
        //record_type = "present-proof";
      // } else if (message_type.endsWith("present-proof/2.0/request-presentation")) {
      //   const resp = await this.admin_GET("/present-proof-2.0/records", { params: { thread_id } });
      //   const resp_json = await resp.json();
      //   record_id = resp_json.results[0].pres_ex_id;
      //   record_type = "present-proof";
      } else {
        return { status: 500, message: `Unsupported message type '${message_type}'` };
      }

      formatted_attachments.push({ id: record_id, type: record_type });
    }

    const data: any = {
      use_public_did: invitationDetails.use_public_did || false,
      attachments: formatted_attachments,
    };

    if (!handshake_protocols && !formatted_attachments.length) {
      data.handshake_protocols = ["did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/didexchange/1.0"];
    } else {
      data.handshake_protocols = handshake_protocols || [];
    }

    if (use_did_method) {
      data.use_did_method = use_did_method;
    }

    if (use_did) {
      data.use_did = use_did;
    }

    if (invitationDetails.mediation_id) {
      data.mediation_id = invitationDetails.mediation_id;
    }

    return data;
  }
}