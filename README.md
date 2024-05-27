# No-Code-AGI                                                   
Requirements.txt

fastapi uvicorn sqlalchemy pydantic

Running the Application

Backend                                                            
1 Navigate to the backend directory:
cd backend

2 Build the Docker image:
docker build -t openagi-backend .

3 Run the Docker container:
docker run -d -p 8000:80 openagi-backend

Frontend

1 Navigate to the frontend directory:
cd frontend

2 Build the Docker image:
docker build -t openagi-frontend .

3 Run the Docker container
docker run -d -p 3000:80 openagi-frontend

Now you should have both the backend and frontend running in Docker containers. The backend will be accessible at http://localhost:8000 and the frontend at http://localhost:3000









