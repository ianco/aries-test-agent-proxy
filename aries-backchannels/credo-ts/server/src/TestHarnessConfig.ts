import {
  HttpOutboundTransport,
  WsOutboundTransport,
  InboundTransport,
  OutboundTransport,
  KeyType,
  TypedArrayEncoder,
} from '@credo-ts/core'
import { HttpInboundTransport, WsInboundTransport } from '@credo-ts/node'
import { $log } from '@tsed/common'
import { createAgent, TestAgent } from './TestAgent'
import { getGenesisPath, getRandomSeed, registerPublicDid } from './utils/ledgerUtils'
import { indyDidFromPublicKeyBase58 } from '@credo-ts/core/build/utils/did'
import { Injectable } from '@tsed/di'

@Injectable()
export class TestHarnessConfig {
  private _createAgentArgs?: CreateAgentArguments
  private agentPorts: AgentPorts

  public readonly backchannelPort: number

  private externalHost: string
  private dockerHost: string
  private runMode?: string

  private _agent?: TestAgent

  private _controllers: (() => void)[] = []

  public constructor({ backchannelPort }: { backchannelPort: number }) {
    this.agentPorts = {
      http: backchannelPort + 1,
      ws: backchannelPort + 2,
    }

    this.backchannelPort = backchannelPort

    this.dockerHost = process.env.DOCKERHOST ?? 'host.docker.internal'
    this.runMode = process.env.RUN_MODE
    this.externalHost = this.runMode === 'docker' ? this.dockerHost : 'localhost'
  }

  public addController(controller: () => void): void {
    $log.info('Register controller')
    this._controllers.push(controller)
  }

  public get agent() {
    if (!this._agent) {
      throw new Error('Agent not initialized')
    }

    return this._agent
  }

  public async startAgent(options: { inboundTransports: Transport[]; outboundTransports: Transport[] }) {
    const agentArgs = await this.getAgentArgs(options)

    this._agent = await createAgent(agentArgs)

    const key = await this._agent.context.wallet.createKey({keyType: KeyType.Ed25519, privateKey: TypedArrayEncoder.fromString(agentArgs.publicDidSeed)})

    const didInfo = {
      did: indyDidFromPublicKeyBase58(key.publicKeyBase58),
      verkey: key.publicKeyBase58
    }
    await this.agent.genericRecords.save({ content: { didInfo }, id: 'PUBLIC_DID_INFO' })
  }

  public async agentStartup() {
    // Call handlers
    for (const controller of this._controllers) {
      await controller()
    }
  }

  public async stopAgent() {
    await this.agent.shutdown()
  }

  private async getAgentArgs(options: { inboundTransports: Transport[]; outboundTransports: Transport[] }) {
    let agentArgs = this._createAgentArgs
    if (!agentArgs) {
      const agentName = process.env.AGENT_NAME ? `Credo ${process.env.AGENT_NAME}` : `Credo Agent (${this.agentPorts.http})`

      // There are multiple ways to retrieve the genesis file
      // we account for all of them
      const genesisFile = process.env.GENESIS_FILE
      const genesisUrl = process.env.GENESIS_URL
      const ledgerUrl = process.env.LEDGER_URL ?? `http://${this.externalHost}:9000`
      const genesisPath = await getGenesisPath(genesisFile, genesisUrl, ledgerUrl, this.dockerHost)

      // Register public did
      const publicDidSeed = getRandomSeed()

      await registerPublicDid(ledgerUrl, publicDidSeed)

      agentArgs = {
        agentName,
        publicDidSeed,
        genesisPath,
      }

      this._createAgentArgs = agentArgs
    }

    return { ...agentArgs, transport: this.getTransportConfig(options) }
  }

  private getTransportConfig(options: {
    inboundTransports: Transport[]
    outboundTransports: Transport[]
  }): TransportConfig {
    const inbound: InboundTransport[] = []
    const outbound: OutboundTransport[] = []
    const endpoints: string[] = []

    for (const inboundTransport of options.inboundTransports) {
      const InboundTransport = inboundTransportMapping[inboundTransport]
      inbound.push(new InboundTransport({ port: this.agentPorts[inboundTransport] }))

      endpoints.push(this.getAgentEndpoint(inboundTransport))
    }

    for (const outboundTransport of options.outboundTransports) {
      const OutboundTransport = outboundTransportMapping[outboundTransport]
      outbound.push(new OutboundTransport())
    }

    return {
      inboundTransports: inbound,
      outboundTransports: outbound,
      endpoints,
    }
  }

  private getAgentEndpoint(transport: Transport) {
    const port = this.agentPorts[transport].toString()

    // may be set via ngrok. Not supported for WS
    const agentEndpoint = process.env.AGENT_PUBLIC_ENDPOINT
    if (transport == 'http' && agentEndpoint) {
      return agentEndpoint
    } else if (process.env.RUN_MODE == 'pwd') {
      return `${transport}://${this.externalHost}`.replace('{PORT}', port)
    }

    return `${transport}://${this.externalHost}:${port}`
  }
}

export interface CreateAgentArguments {
  agentName: string
  publicDidSeed: string
  genesisPath: string
  useLegacyIndySdk?: boolean
}

export interface AgentPorts {
  http: number
  ws: number
}

export type Transport = 'http' | 'ws'

const inboundTransportMapping = {
  http: HttpInboundTransport,
  ws: WsInboundTransport,
} as const

const outboundTransportMapping = {
  http: HttpOutboundTransport,
  ws: WsOutboundTransport,
} as const

export interface TransportConfig {
  inboundTransports: InboundTransport[]
  outboundTransports: OutboundTransport[]
  endpoints: string[]
}
