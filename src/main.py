import os
import pickle
import string

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import SessionLocal, engine
from .features import calculate_features

models.Base.metadata.create_all(bind=engine)

PASSWORD = "c716d7f65958fc43f32642b3f42b761de6"
app = FastAPI()

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")



# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_session(request: Request):
    return request.session

@app.post("/register")
async def register(request: Request,response:Response, db: Session = Depends(get_db)):
    error=[]
    success=[]
    data = await request.form()
    email = data.get("email")
    password = data.get("pswd")     
    confirm_pass= data.get("confirmpswd")   
    user = models.User(email=email, hashed_password=password)
    if confirm_pass:
        # registration
        if password!=confirm_pass:
            return RedirectResponse('/register', status_code=303)
        crud.create_user(db=db, user=user)
        return templates.TemplateResponse("logreg.html", {"request": request, "user": [data,email,password]})
    else:
        # login/sign in
        try:
            print("qwertyuiop")
            user=db.query(models.User).filter(models.User.email==email).first()
            if user is None:
                error.append("Email does not exists")
                print("Error user in none")
                reply={"request":request,"error":error}
                return templates.TemplateResponse('logreg.html',reply)
            else:
                print("password")
                if password==user.hashed_password:
                    print(password)
                    data = {"sub":email}
                    jwt_token = jwt.encode(data,PASSWORD,algorithm="HS256")
                    success.append("Login Successfully")
                    reply={"request":request,"error":error,"success":success}
                    response = RedirectResponse(url="/")
                    response.set_cookie(key="access_token",value=f"Bearer {jwt_token}",httponly=True)
                    return response
                else:
                    error.append("Invalid password")
        except:  
            print("jk")
            error.append("Unexpected error!!!")
            reply={"request":request,"error":error}
            return templates.TemplateResponse('logreg.html',reply)



@app.get("/register")
async def register_get(request: Request):
    access_token = request.cookies.get("access_token")

    if access_token:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("logreg.html", {"request": request})



@app.get("/logout")
async def logout(request: Request,response: Response):
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    access_token = request.cookies.get("access_token")

    if access_token:
        try:
            decoded_token = jwt.decode(access_token.split("Bearer ")[1],PASSWORD, algorithms=["HS256"])
            email = decoded_token.get("sub")
            # Perform additional checks or actions based on the email or other token data

            # User is logged in, show the home page
            reply= {"request": request, "logged_in": [True,email]}
        except:
            # Invalid token, user is not logged in
            reply= {"request": request, "logged_in": False}
        return templates.TemplateResponse("home.html",reply)

    # No access token found, user is not logged in
    reply= {"request": request, "logged_in": False}
    return templates.TemplateResponse("home.html", reply)

@app.post("/")
async def index_post(request: Request):
    return RedirectResponse(url="/", status_code=303)

@app.get("/delete-his/{item_id}")
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.Sequences).filter(models.Sequences.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
        return RedirectResponse(url='/history')
    else:
        return {"message": "Item not found"}

@app.post("/detail/{item_id}")
async def edit_item(request:Request,item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.Sequences).filter(models.Sequences.id == item_id).first()
    data = await request.form()
    if item and data:
        item.name = data['name']
        item.description = data['desc']
        db.commit()
        return {"message": "Item updated"}
    else:
        return {"message": "Item not found"}

@app.get("/detail/{user_id}")
async def details(request: Request,user_id: int,  db: Session = Depends(get_db)):
        access_token = request.cookies.get("access_token")
        logged_in=False
        history_detail=None
        value=None
        if access_token:
            decoded_token = jwt.decode(access_token.split("Bearer ")[1], PASSWORD, algorithms=["HS256"])
            email = decoded_token.get("sub")
            logged_in=True
            history_detail = db.query(models.Sequences).filter(models.Sequences.id == user_id)
            if history_detail[0].result:
                value=history_detail[0].result.split(",")
        reply={"request": request,"history":history_detail,"logged_in":logged_in,"value":value}
        return templates.TemplateResponse("details.html", reply)
    

@app.get("/history")
async def his(request: Request, db: Session = Depends(get_db)):  
        access_token = request.cookies.get("access_token")
        history=None
        logged_in=False
        if access_token:
            decoded_token = jwt.decode(access_token.split("Bearer ")[1], PASSWORD, algorithms=["HS256"])
            email = decoded_token.get("sub")
            history = db.query(models.Sequences).filter(models.Sequences.owner_id == email)
            logged_in=True
        reply={"request": request,"history":history,"logged_in":logged_in}
        return templates.TemplateResponse("history.html", reply)



# ML model  
@app.get("/submit")
async def register_form(request: Request): 
        return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def submit_form(request: Request, db: Session = Depends(get_db)):
      
    data = await request.form()
    value = data.get("rna").upper()
    if value:
        set_value = set(value)
        rna_seq_poss = {'A','T','G','C'}
        for s in set_value:
            if s not in rna_seq_poss:
                return templates.TemplateResponse("form.html", {"request": request,"error": "Should only use A,C,T,G"})


    name = data.get("name")
    desc = data.get("desc")
    decoded_token=None
    email=None
    logged_in=False
    access_token = request.cookies.get("access_token")
    if access_token:
        decoded_token = jwt.decode(access_token.split("Bearer ")[1],PASSWORD, algorithms=["HS256"])
        email = decoded_token.get("sub")
        logged_in=True
    if value:
        model_path = os.path.join(os.getcwd(), 'model.pkl')
        model = pickle.load(open(model_path, 'rb'))
        seq=value.translate({ord(c): None for c in string.whitespace})
        features = calculate_features(seq)
        result=model.predict(features)
        r=f"{features[0][0]},{features[0][1]},{features[0][2]},{features[0][3]},{features[0][4]},{result[0]}"
        if decoded_token:
            sequence = models.Sequences(name=name, seq=value,
                                        description=desc,result=r,
                                        owner_id=email)
            crud.create_seq(db=db, seq=sequence)
    else:
        seq=''
        features=None
        result=None


    reply={"request": request,"text":value,'seq':seq,
           'features':features,'result':result,"logged_in":logged_in}
    return templates.TemplateResponse("form.html", reply)




# api
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user_api(db=db, user=user)
