# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR .

# Copy the current directory contents into the container at /app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8090 available to the world outside this container
EXPOSE 8090

# Define environment variable
ENV PYTHONHASHSEED=0

# Run main.py when the container launches
CMD ["python", "main.py"]