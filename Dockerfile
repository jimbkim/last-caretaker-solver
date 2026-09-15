FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY solver.py webapp.py solve_all.py ./
COPY data ./data
COPY plan.json global_plan.json ./state-seed/
RUN mkdir -p /app/state && cp /app/state-seed/*.json /app/state/
EXPOSE 8765
VOLUME ["/app/state"]
ENV SOLVER_STATE=/app/state
CMD ["python", "webapp.py", "0.0.0.0"]
