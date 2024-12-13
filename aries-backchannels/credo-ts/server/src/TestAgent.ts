import { $log } from '@tsed/common'
import { Agent, AgentEventTypes, AgentMessageProcessedEvent, AutoAcceptCredential, AutoAcceptProof, CredentialsModule, DidsModule, InitConfig, MediatorModule, ProofsModule, V2CredentialProtocol, V2ProofProtocol, KeyDidCreateOptions } from '@credo-ts/core'
import { agentDependencies } from '@credo-ts/node'
import { AskarModule } from '@credo-ts/askar'
import { AnonCredsModule, LegacyIndyCredentialFormatService, LegacyIndyProofFormatService,  V1CredentialProtocol, V1ProofProtocol, AnonCredsCredentialFormatService, AnonCredsProofFormatService } from '@credo-ts/anoncreds'
//import { AnonCredsRsModule } from '@aries-framework/anoncreds-rs'
import { IndyVdrAnonCredsRegistry, IndyVdrModule, IndyVdrSovDidResolver, IndyVdrIndyDidResolver, IndyVdrPoolConfig, IndyVdrIndyDidRegistrar } from '@credo-ts/indy-vdr'
import { TsedLogger } from './TsedLogger'
import { anoncreds } from '@hyperledger/anoncreds-nodejs'
import { ariesAskar } from '@hyperledger/aries-askar-nodejs'
import { indyVdr } from '@hyperledger/indy-vdr-nodejs'
import { HttpInboundTransport } from '@credo-ts/node'

export type TestAgent = Agent<ReturnType<typeof getAskarAnonCredsIndyModules>>

export async function createAgent({
  genesisPath,
  agentName,
  transport,
}: {
  genesisPath: string
  agentName: string
  transport: TransportConfig
  useLegacyIndySdk?: boolean
}) {
  const agentConfig: InitConfig = {
    label: agentName,
    walletConfig: {
      id: `aath-credo-${Date.now()}`,
      key: '00000000000000000000000000000Test01',
    },
    endpoints: transport.endpoints,
    useDidSovPrefixWhereAllowed: true,
    logger: new TsedLogger($log),
  }

  const genesisTransactions = await new agentDependencies.FileSystem().read(genesisPath)

  const modules = getAskarAnonCredsIndyModules({
    //indyNamespace: 'main-pool',
    indyNamespace: 'bcovrin:test',
    isProduction: false,
    genesisTransactions,
    // connectOnStartup: true, //TODO Should we do this in the test agent? We never did but all sample code I see includeing the demo does this
  })

  const agent = new Agent({ config: agentConfig, dependencies: agentDependencies,
    modules
  })

  for (const it of transport.inboundTransports) {
    agent.registerInboundTransport(it)
  }

  for (const ot of transport.outboundTransports) {
    agent.registerOutboundTransport(ot)
  }

  await agent.initialize()

  // If at least a link secret is found, we assume there is a default one
  if ((await agent.modules.anoncreds.getLinkSecretIds()).length === 0) {
    await agent.modules.anoncreds.createLinkSecret()
  }


  agent.events.on(AgentEventTypes.AgentMessageProcessed, (data: AgentMessageProcessedEvent) => {
    agent.config.logger.debug(`Processed inbound message: ${JSON.stringify(data.payload.message.toJSON())}`)
  })

  return agent
}

export function getAskarAnonCredsIndyModules(indyNetworkConfig: IndyVdrPoolConfig) {
  const legacyIndyCredentialFormatService = new LegacyIndyCredentialFormatService()
  const legacyIndyProofFormatService = new LegacyIndyProofFormatService()

  return {
    mediator: new MediatorModule({
    // Needed to accept mediation requests: https://github.com/hyperledger/aries-framework-javascript/issues/668
    autoAcceptMediationRequests: true,
    }),
    credentials: new CredentialsModule({
      autoAcceptCredentials: AutoAcceptCredential.Never,
      credentialProtocols: [
        new V1CredentialProtocol({
          indyCredentialFormat: legacyIndyCredentialFormatService,
        }),
        new V2CredentialProtocol({
          // Credo Update - added AnonCredsCredentialFormatService as shown here, https://credo.js.org/guides/tutorials/issue-an-anoncreds-credential-over-didcomm#issuer
          credentialFormats: [legacyIndyCredentialFormatService, new AnonCredsCredentialFormatService()],
        }),
      ],
    }),
    proofs: new ProofsModule({
      autoAcceptProofs: AutoAcceptProof.Never,
      proofProtocols: [
        new V1ProofProtocol({
          indyProofFormat: legacyIndyProofFormatService,
        }),
        new V2ProofProtocol({
          proofFormats: [legacyIndyProofFormatService, new AnonCredsProofFormatService],
        }),
      ],
    }),
    anoncreds: new AnonCredsModule({
      registries: [new IndyVdrAnonCredsRegistry()],
      anoncreds,
    }),
    //anoncredsRs: new AnonCredsRsModule({ anoncreds }),
    indyVdr: new IndyVdrModule({
      indyVdr,
      networks: [indyNetworkConfig],
    }),
    dids: new DidsModule({
      // Credo Update - added from registrars: [new IndyVdrIndyDidRegistrar()], as shown here, https://credo.js.org/guides/tutorials/issue-an-anoncreds-credential-over-didcomm#issuer
      registrars: [new IndyVdrIndyDidRegistrar()],
      resolvers: [new IndyVdrSovDidResolver(), new IndyVdrIndyDidResolver()],
    }),
    askar: new AskarModule({ ariesAskar }),
  } as const
}
