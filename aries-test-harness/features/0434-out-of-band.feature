@RFC0434 @AIP20
Feature: RFC 0434 Intiating exchange using the Out of Band protocol
   In order to intiate the exchange with another agent,
   As a sender or a receiver,
   I want to use Out of Band(RFC0434) protocols to accomplish this.


   @T001-RFC0434 @RFC0036 @critical @AcceptanceTest
   Scenario Outline: Issue a v1 indy credential using connectionless out of band invitation
      Given we have "2" agents
         | name | role   |
         | Acme | issuer |
         | Bob  | holder |
      Given "Acme" is ready to issue a "<credential_format>" credential
      When "Acme" creates a credential offer
      And "Acme" sends a connectionless out of band invitation to "Bob" with "credential-offer"
      And "Bob" receives the invitation
      And "Bob" requests the credential
      And "Acme" issues the credential
      And "Bob" acknowledges the credential issue
      Then "Bob" has the credential issued

      @CredFormat_Indy
      Examples:
         | credential_format |
         | indy              |

   @T002-RFC0434 @RFC0453 @critical @AcceptanceTest @Schema_DriversLicense_v2 
   Scenario Outline: Issue a v2 credential using connectionless out of band invitation
      Given we have "2" agents
         | name | role   |
         | Acme | issuer |
         | Bob  | holder |
      Given "Acme" is ready to issue a "<credential_format>" credential
      When "Acme" creates an "<credential_format>" credential offer with <credential_data>
      And "Acme" sends a connectionless out of band invitation to "Bob" with "credential-offer"
      And "Bob" receives the invitation
      And "Bob" requests the "<credential_format>" credential
      And "Acme" issues the "<credential_format>" credential
      And "Bob" acknowledges the "<credential_format>" credential issue
      Then "Bob" has the "<credential_format>" credential issued

      @CredFormat_Indy @RFC0592
      Examples:
         | credential_format | credential_data   |
         | indy              | Data_DL_MaxValues |

      @CredFormat_Anoncreds @RFC0592 @Anoncreds
      Examples:
         | credential_format | credential_data   |
         | anoncreds         | Data_DL_MaxValues |

      @CredFormat_JSON-LD @RFC0593 @ProofType_Ed25519Signature2018 @DidMethod_key
      Examples:
         | credential_format | credential_data   |
         | json-ld           | Data_DL_MaxValues |

   @T003-RFC0434 @RFC0037 @critical @AcceptanceTest @Indy
   Scenario: Present a v1 indy proof using connectionless out of band invitation
      Given we have "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Bob" has an issued credential from Acme
      When "Faber" creates a proof request
      And "Faber" sends a connectionless out of band invitation to "Bob" with "proof-request"
      And "Bob" receives the invitation
      And "Bob" makes the presentation of the proof
      And "Faber" acknowledges the proof
      Then "Bob" has the proof verified

   @T004-RFC0434 @RFC0454 @critical @AcceptanceTest @Schema_DriversLicense_v2 @CredProposalStart
   Scenario Outline: Present a v2 proof using connectionless out of band invitation
      Given we have "2" agents
         | name  | role     |
         | Faber | verifier |
         | Bob   | prover   |
      And "Bob" has an issued credential with formats from Acme with <credential_data>
      When "Faber" creates a "<request_for_proof>" proof request
      And "Faber" sends a connectionless out of band invitation to "Bob" with "proof-request"
      And "Bob" receives the invitation
      And "Bob" makes the <presentation> of the proof with formats
      And "Faber" acknowledges the proof with formats
      Then "Bob" has the proof with formats verified

      @CredFormat_Indy @RFC0592
      Examples:
         | credential_data   | request_for_proof           | presentation               |
         | Data_DL_MaxValues | proof_request_DL_address_v2 | presentation_DL_address_v2 |

      @CredFormat_Anoncreds @RFC0592 @Anoncreds
      Examples:
         | credential_data   | request_for_proof           | presentation               |
         | Data_DL_MaxValues | proof_request_DL_address_v2 | presentation_DL_address_v2 |

      @CredFormat_JSON-LD @RFC0510 @Schema_DriversLicense_v2 @CredProposalStart @ProofType_Ed25519Signature2018 @DidMethod_key
      Examples:
         | issuer | credential_data   | request_for_proof                  | presentation                      |
         | Acme   | Data_DL_MaxValues | proof_request_DL_address_v2_dif_pe | presentation_DL_address_v2_dif_pe |
