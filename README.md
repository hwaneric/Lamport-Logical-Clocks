# Lamport-Logical-Clocks
A model of a distributed system using Lamport Logical clocks to sequence events

# Getting Started Locally
To start running our project locally, first create a Python virtual environment in the root directory by running ```python -m venv venv```. Then activate the venv by running the OS appropriate script as noted in this article: https://www.geeksforgeeks.org/create-virtual-environment-using-venv-python/#

Once the venv is active, download the project requirements by running ```pip3 install -r requirements.txt```.

Also in the root directory, create a .env file, which is where we store sensitive configuration details. You will need the following configuration variables:
```
HOST_1="{Host of Machine 1}"
PORT_1={Port of Machine 1}
HOST_2="{Host of Machine 2}"
PORT_2={Port of Machine 1}
HOST_3="{Host of Machine 3}"
PORT_3={Port of Machine 1}
```
Our project is set up to simulate running all 3 machines on the same computer (by creating a new process for each of the machines). As such, you will likely need to specify the HOST variables to "localhost".

Once the above configuration steps are complete, you should be able to run the project! To run the experiment, run the ```driver.py``` file. 

# Running Tests
To run our test suite, cd into the tests folder and run ```pytest``` in the terminal.
