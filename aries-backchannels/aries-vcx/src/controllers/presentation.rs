use std::sync::Mutex;
use std::collections::HashMap;
use actix_web::{web, Responder, post, get};
use uuid;
use crate::error::{HarnessError, HarnessErrorType, HarnessResult};
use crate::{Agent, State};
use crate::controllers::Request;
use vcx::aries::messages::proof_presentation::presentation_request::PresentationRequest as VcxPresentationRequest;
use vcx::aries::messages::proof_presentation::presentation_request::PresentationRequestData;
use vcx::aries::messages::attachment::Attachments;
use vcx::aries::handlers::proof_presentation::verifier::verifier::Verifier;
use vcx::aries::handlers::proof_presentation::prover::prover::Prover;
use vcx::aries::messages::a2a::A2AMessage;
use vcx::api::VcxStateType;
use vcx::aries::messages::status::Status;

#[derive(Serialize, Deserialize, Default, Debug)]
struct PresentationProposal {
    connection_id: String,
    presentation_proposal: PresentationRequest
}

#[derive(Debug, Deserialize, Serialize, Clone, PartialEq, Default)]
pub struct PresentationRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub comment: Option<String>,
    #[serde(rename = "request_presentations~attach")]
    pub request_presentations_attach: Attachments,
}

#[derive(Serialize, Deserialize, Debug, PartialEq, Clone)]
pub struct ProofRequestData {
    pub requested_attributes: serde_json::Value,
}

fn _get_state_prover(prover: &Prover) -> State {
    match VcxStateType::from_u32(prover.state()) {
        VcxStateType::VcxStateInitialized => State::Initial,
        VcxStateType::VcxStateOfferSent => State::PresentationSent,
        VcxStateType::VcxStateRequestReceived => State::RequestReceived,
        VcxStateType::VcxStateAccepted => State::Done,
        _ => State::Unknown
    }
}

fn _get_state_verifier(verifier: &Verifier) -> State {
    match VcxStateType::from_u32(verifier.state()) {
        VcxStateType::VcxStateInitialized => State::Initial,
        VcxStateType::VcxStateOfferSent => State::OfferSent,
        VcxStateType::VcxStateRequestReceived => State::RequestReceived,
        VcxStateType::VcxStateAccepted => State::PresentationReceived,
        _ => State::Unknown
    }
}

fn _select_credentials(resolved_creds: &str) -> HarnessResult<String> {
    let resolved_creds: HashMap<String, HashMap<String, serde_json::Value>> = serde_json::from_str(resolved_creds).map_err(|err| HarnessError::from(err))?;
    let resolved_creds: HashMap<String, serde_json::Value> = resolved_creds.get("attrs")
        .ok_or(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("No attrs in resolved_creds: {:?}", resolved_creds)))?.clone();
    let mut selected_creds: HashMap<String, HashMap<String, serde_json::Value>> = HashMap::new();
    selected_creds.insert(String::from("attrs"), HashMap::new());
    for (attr_name, attr_cred_info) in resolved_creds.iter() {
        match attr_cred_info {
            serde_json::Value::Array(attr_cred_info) => {
                if attr_cred_info.len() > 0 {
                    selected_creds.get_mut("attrs").unwrap().insert(String::from(attr_name), json!({
                        "credential": attr_cred_info.first().unwrap()
                    }));
                }
            }
            _ => return Err(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("Unexpected data, expected attr_cred_info to be an array, but got {:?}.", attr_cred_info)))
        }
    }
    serde_json::to_string(&selected_creds).map_err(|err| HarnessError::from(err))
}

impl Agent {
    pub fn send_proof_request(&mut self, presentation_proposal: &PresentationProposal) -> HarnessResult<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let connection = self.last_connection.as_ref()
            .ok_or(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("No connection established")))?;
        let content = presentation_proposal.presentation_proposal.request_presentations_attach.content().map_err(|err| HarnessError::from(err))?;
        let req_data: ProofRequestData = serde_json::from_str(&content).map_err(|err| HarnessError::from(err))?;
        let requested_attrs = req_data.requested_attributes.to_string();
        let mut verifier = Verifier::create(id.to_string(), requested_attrs, "[]".to_string(), "{}".to_string(), id.to_string()).map_err(|err| HarnessError::from(err))?;
        verifier.send_presentation_request(connection.send_message_closure().map_err(|err| HarnessError::from(err))?, None).map_err(|err| HarnessError::from(err))?;
        self.db.set(&id, &verifier).map_err(|err| HarnessError::from(err))?;
        Ok(json!({"state": State::RequestSent, "thread_id": id}).to_string())
    }

    pub fn send_presentation(&mut self, id: &str) -> HarnessResult<String> {
        let mut prover: Prover = self.db.get(id)
            .ok_or(HarnessError::from_msg(HarnessErrorType::NotFoundError, &format!("Prover with id {} not found", id)))?;
        let connection = self.last_connection.as_ref()
            .ok_or(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("No connection established")))?;
        let credentials = prover.retrieve_credentials().map_err(|err| HarnessError::from(err))?;
        let credentials = _select_credentials(&credentials)?;
        prover.generate_presentation(credentials, "{}".to_string()).map_err(|err| HarnessError::from(err))?;
        prover.send_presentation(&connection.send_message_closure().map_err(|err| HarnessError::from(err))?).map_err(|err| HarnessError::from(err))?;
        self.db.set(&id, &prover).map_err(|err| HarnessError::from(err))?;
        Ok(json!({"state": _get_state_prover(&prover), "thread_id": id}).to_string())
    }

    pub fn verify_presentation(&mut self, id: &str) -> HarnessResult<String> {
        let mut verifier: Verifier = self.db.get(id)
            .ok_or(HarnessError::from_msg(HarnessErrorType::NotFoundError, &format!("Verifier with id {} not found", id)))?;
        let connection = self.last_connection.as_ref()
            .ok_or(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("No connection established")))?;
        verifier.update_state(connection).map_err(|err| HarnessError::from(err))?;
        self.db.set(&id, &verifier).map_err(|err| HarnessError::from(err))?;
        match Status::from_u32(verifier.presentation_status()) {
            Status::Success => Ok(json!({"state": State::Done}).to_string()), // TODO: Check we are in final state
            _ => Ok(json!({"state": State::Failure}).to_string())
        }
    }

    pub fn get_proof(&mut self, id: &str) -> HarnessResult<String> {
        let connection = self.last_connection.as_ref()
            .ok_or(HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("No connection established")))?;
         match self.db.get::<Prover>(id) {
             Some(mut prover) => {
                 prover.update_state(connection).map_err(|err| HarnessError::from(err))?;
                 self.db.set(&id, &prover).map_err(|err| HarnessError::from(err))?;
                 let state = _get_state_prover(&prover);
                 Ok(json!({ "state": state }).to_string())
             }
             None => match self.db.get::<Verifier>(id) {
                 None => {
                     let presentation_requests: Vec<VcxPresentationRequest> =
                         connection.get_messages()?
                             .into_iter()
                             .filter_map(|(_, message)| {
                                 match message {
                                     A2AMessage::PresentationRequest(presentation_request) => Some(presentation_request),
                                     _ => None
                                 }
                             }).collect();
                     let presentation_request = presentation_requests.first()
                        .ok_or(
                            HarnessError::from_msg(HarnessErrorType::InternalServerError, &format!("Did not obtain presentation request message"))
                        )?;
                     let prover = Prover::create(id, presentation_request.clone())?;
                     self.db.set(&id, &prover).map_err(|err| HarnessError::from(err))?;
                     let state = _get_state_prover(&prover);
                     Ok(json!({ "state": state }).to_string())
                }
                Some(mut verifier) => {
                     verifier.update_state(connection).map_err(|err| HarnessError::from(err))?;
                     self.db.set(&id, &verifier).map_err(|err| HarnessError::from(err))?;
                     let state = _get_state_verifier(&verifier);
                     Ok(json!({ "state": state }).to_string())
                }
             }
         }
    } 
}

#[post("/send-request")]
pub async fn send_proof_request(req: web::Json<Request<PresentationProposal>>, agent: web::Data<Mutex<Agent>>) -> impl Responder {
    agent.lock().unwrap().send_proof_request(&req.data)
}

#[post("/send-presentation")]
pub async fn send_presentation(req: web::Json<Request<serde_json::Value>>, agent: web::Data<Mutex<Agent>>) -> impl Responder {
    agent.lock().unwrap().send_presentation(&req.id)
}

#[post("/verify-presentation")]
pub async fn verify_presentation(req: web::Json<Request<serde_json::Value>>, agent: web::Data<Mutex<Agent>>) -> impl Responder {
    agent.lock().unwrap().verify_presentation(&req.id)
}

#[get("/{proof_id}")]
pub async fn get_proof(agent: web::Data<Mutex<Agent>>, path: web::Path<String>) -> impl Responder {
    agent.lock().unwrap().get_proof(&path.into_inner())
        .with_header("Cache-Control", "private, no-store, must-revalidate")
}
pub fn config(cfg: &mut web::ServiceConfig) {
    cfg
        .service(
            web::scope("/command/proof")
                .service(send_proof_request)
                .service(send_presentation)
                .service(verify_presentation)
                .service(get_proof)
        );
}