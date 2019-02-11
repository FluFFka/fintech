import sys
sys.path.append("C:\Solc")
sys.path.append("C:\Python_Interpreter\Lib\site-packages")

from eth_abi import encode_abi
import json
import requests
from solc import compile_source
from web3 import Web3, HTTPProvider
import argparse
from eth_account import Account

class Owner(object):
    def __init__(self, address, privateKey):
        self.address = address
        self.privateKey = privateKey
    def addContract(self, contract):
        self.possessedContract = contract

def extractPrivateKey():
    account = open("account.json", 'r')
    privateKey = eval(account.read())["account"]
    account.close()
    return privateKey

def generateAddressFromPrivateKey(privateKey):
    privateKey = "0x" + str(privateKey)
    return str((Account.privateKeyToAccount(privateKey)).address)

def getContractSource(ownerAddress):
    soliditySource = '''
    pragma solidity ^0.4.24;

    contract Mortal {
        address owner;

        constructor() public {
            require(%s != address(0));
            owner = %s;
        }

        modifier ownerOnly {
            require(msg.sender == owner);
            _;
        }
    }

    contract KYC is Mortal {

        mapping (address => string) addressToCustomerName;
        mapping (string => address[]) customerNameToAddress;

        function addCustomer(string memory customerName) public {
            require(msg.sender != address(0));
            require(msg.sender == tx.origin);
            addressToCustomerName[msg.sender] = customerName;
            customerNameToAddress[customerName].push(msg.sender);
        }

        function deleteCustomer() public {
            require(msg.sender != address(0));
            require(msg.sender == tx.origin);
            string memory name = addressToCustomerName[msg.sender];
            addressToCustomerName[msg.sender] = '';
            uint _length = customerNameToAddress[name].length;
            for (uint i = 0; i < _length; ++i) {
                customerNameToAddress[name][i] = 0x0000000000000000000000000000000000000000;
            }
        }

        function retrieveName(address customerAddress) public returns (string memory) {
            return addressToCustomerName[customerAddress];
        }

        function retrieveAddresses(string memory customerName) public returns (address[]) {
            return customerNameToAddress[customerName];
        }

        function isAddressUsed(address customerAddress) public returns (bool) {
            return bytes(addressToCustomerName[customerAddress]).length != 0;
        }

        function () external payable {}

        function deleteContract() public ownerOnly {
            selfdestruct(address(owner));
        }
    }
    ''' % (ownerAddress, ownerAddress)
    return soliditySource

# utils

HexBytes = lambda x: x

def getGasPrice(speed):
    response = requests.get("https://gasprice.poa.network")
    return int((response.json())[speed] * 1e9)

def cleanTxResponse(rawReceipt):
    return eval(str(rawReceipt)[14:-1]) if rawReceipt is not None else None

# essential

def deployContract(server, owner):
    contractData = {}
    contractSource = getContractSource(owner.address)
    compiledSource = compile_source(contractSource)
    contractInterface = compiledSource["<stdin>:KYC"]
    contractData["abi"] = contractInterface['abi']
    rawKYC = server.eth.contract(abi=contractInterface['abi'], bytecode=contractInterface['bin'])
    gasCost = server.eth.estimateGas({"to": None, "value": 0, "data": rawKYC.bytecode})
    tx = {
        "nonce": server.eth.getTransactionCount(owner.address),
        "gasPrice": getGasPrice(speed="fast"),
        "gas": gasCost,
        "to": None,
        "value": 0,
        "data": rawKYC.bytecode
    }
    contractDeploymentTransactionSigned = server.eth.account.signTransaction(
        tx,
        extractPrivateKey()
    )
    deploymentHash = server.eth.sendRawTransaction(contractDeploymentTransactionSigned.rawTransaction)
    txReceipt = server.eth.waitForTransactionReceipt(deploymentHash)
    contractData["contractAddress"] = cleanTxResponse(txReceipt)["contractAddress"]
    contract = server.eth.contract(
        address=contractData["contractAddress"],
        abi=contractData["abi"],
    )
    file = open("database.json", "w+")
    startBlock = cleanTxResponse(txReceipt)["blockNumber"]
    dataToStore = {
        "registrar": contract.address,
        "startBlock": startBlock,
    }
    file.write(str(dataToStore))
    file.close()
    return contract

def invokeContract(server, sender, contract, methodSig, methodName, methodArgs, methodArgsTypes, value=0):

    methodSignature = server.sha3(text=methodSig)[0:4].hex()
    params = encode_abi(methodArgsTypes, methodArgs)
    payloadData = "0x" + methodSignature + params.hex()
    estimateData = {
        "to": contract.address,
        "value": value,
        "data": payloadData
    }
    rawTX = {
        "to": contract.address,
        "data": payloadData,
        "value": value,
        "from": sender.address,
        "nonce": server.eth.getTransactionCount(sender.address),
        "gasPrice": getGasPrice(speed="fast"),
    }
    gas = server.eth.estimateGas(rawTX)
    rawTX["gas"] = gas
    signedTX = server.eth.account.signTransaction(
        rawTX,
        sender.privateKey,
    )
    txHash = server.eth.sendRawTransaction(signedTX.rawTransaction).hex()
    return txHash

def callContract(contract, methodName, methodArgs):
    _args = str(methodArgs)[1:-1]
    response = eval("contract.functions.{}({}).call()".format(methodName, _args))
    return response

def getContract(server, owner):
    # fetch contract address from database.json
    db = open("database.json", 'r')
    data = eval(db.read())
    db.close()
    contractAddress = data["registrar"]
    # generate contract abi
    contractSource = getContractSource(owner.address)
    compiledSource = compile_source(contractSource)
    contractInterface = compiledSource["<stdin>:KYC"]
    _abi = contractInterface['abi']
    _contract = server.eth.contract(address=contractAddress, abi=_abi)
    return _contract

def initParser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--deploy", action="store_true", help="Deploy a new contract")
    parser.add_argument("-a", "--add", action="store", help="Bind your name with current address")
    parser.add_argument("-D", "--del", action="store_true", help="Unbind your name from your address")
    global args
    args = parser.parse_args()
    args = vars(args)

def handleArgs(server, owner):
    # US 01-02
    if args["deploy"] == True:
        contract = deployContract(server, owner)
        owner.addContract(contract)
        print("Contract address: {0}".format(contract.address))

    # US 07-10


    # US 03-06
    elif args["add"] == None:
        _contract = getContract(server, owner)
        flag = callContract(
            contract=_contract,
            methodName="isAddressUsed",
            methodArgs=[owner.address],
        )
        if not flag:
            try:
                txHash = invokeContract(
                    server=server,
                    sender=owner,
                    contract=_contract,
                    methodSig="addCustomer(string)",
                    methodName="addCustomer",
                    methodArgs=[str(args["add"])],
                    methodArgsTypes=["string"],
                )
                if len(txHash) == 66:
                    print("Successfully added by {tx}".format(tx=txHash))
                else:
                    print("Error while invoking the contract was occured")
            except ValueError:
                print("No enough funds to add name")
        else:
            print("One account must correspond one name")

    elif args["del"] == True:
        _contract = getContract(server, owner)
        flag = callContract(
            contract=_contract,
            methodName="isAddressUsed",
            methodArgs=[owner.address],
        )
        if flag:
            try:
                txHash = invokeContract(
                server=server,
                sender=owner,
                contract=_contract,
                methodSig="deleteCustomer()",
                methodName="deleteCustomer",
                methodArgs=[],
                methodArgsTypes=[],
                )
                if len(txHash) == 66:
                    print("Successfully deleted by {tx}".format(tx=txHash))
                else:
                    print("Error while invoking the contract was occured")
            except ValueError:
                    print("No enough funds to delete name")
        else:
            print("No name found for your account")

def main():
    initParser()
    print(args)
    server = Web3(HTTPProvider("https://sokol.poa.network"))
    owner = Owner(generateAddressFromPrivateKey(extractPrivateKey()), extractPrivateKey())
    handleArgs(server, owner)

if __name__ == "__main__":
    main()
# CA: 0x922979B074FC62E8ffc68838E33b355Ffd64DA99
# DIR: cd Documents/github/fintech/etc/contract
