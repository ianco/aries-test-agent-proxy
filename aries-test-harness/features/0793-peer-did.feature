# https://github.com/hyperledger/aries-rfcs/tree/main/features/0793-unqualfied-dids-transition

@QualifiedDIDs @RFC0793
Feature: Qualified DID - Unqualified DID Transition
   In order to more effectivley interoperate with other Aries Agents
   as an Aries Framework
   I want to support qualified did:peer DIDs


   @T001-RFC0793 @critical @AcceptanceTest
   Scenario Outline: Establish a connection with DID Exchange between two agents utilizing qualified did:peer DIDs
      Given we have "2" agents
         | name | role      |
         | Acme | requester |
         | Bob  | responder |
      When "Bob" sends an invitation to "Acme" with <peer_did_method>
         | use_public_did | handshake_protocols                 |
         | False          | https://didcomm.org/didexchange/1.1 |
      And "Acme" receives the invitation
      And "Acme" sends the request to "Bob"
      And "Bob" receives the request
      And "Bob" sends a response to "Acme"
      And "Acme" receives the response
      And "Acme" sends complete to "Bob"
      Then "Acme" and "Bob" have a connection

      Examples:
         | peer_did_method |
         | unqualified     |
         #| did:peer:1      |
         | did:peer:2      |
         #| did:peer:3      |
         | did:peer:4      |


   @T002-RFC0793 @critical @AcceptanceTest
   Scenario Outline: Establish a connection with DID Exchange between two agents utilizing qualified did:peer DIDs with responder not set to send qualified Peer DIDs
      Given we have "2" agents
         | name | role      |
         | Acme | requester |
         | Bob  | responder |
      When "Bob" sends an invitation to "Acme" with <peer_did_method>
         | use_public_did | handshake_protocols                 |
         | False          | https://didcomm.org/didexchange/1.1 |
      And "Acme" receives the invitation
      And "Acme" sends the request to "Bob" with <requester_peer_did_method>
      And "Bob" receives the request
      And "Bob" sends a response to "Acme"
      And "Acme" receives the response
      And "Acme" sends complete to "Bob"
      Then "Acme" and "Bob" have a connection

      Examples:
         | peer_did_method | requester_peer_did_method |
         | unqualified     | did:peer:2                |
         | unqualified     | did:peer:4                |


   @T003-RFC0793 @critical @AcceptanceTest
   Scenario Outline: Establish a connection with DID Exchange between two agents utilizing qualified did:peer DIDs with responder set to send a different Peer DID method
      Given we have "2" agents
         | name | role      |
         | Acme | requester |
         | Bob  | responder |
      When "Bob" sends an invitation to "Acme" with <peer_did_method>
         | use_public_did | handshake_protocols                 |
         | False          | https://didcomm.org/didexchange/1.1 |
      And "Acme" receives the invitation
      And "Acme" sends the request to "Bob" with <requester_peer_did_method>
      And "Bob" receives the request
      And "Bob" sends a response to "Acme"
      And "Acme" receives the response
      And "Acme" sends complete to "Bob"
      Then "Acme" and "Bob" have a connection

      Examples:
         | peer_did_method | requester_peer_did_method |
         | did:peer:2      | did:peer:4                |
         | did:peer:4      | did:peer:2                |

