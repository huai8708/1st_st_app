import numpy as np
import os
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
import torch
from torch import nn
import torch.nn.functional as F
import streamlit as st

@st.cache
def readdat():
    data=np.load("data.npz")
    return data
data = readdat()
traindata_x,traindata_y,testdata_x,testdata_y=data['arr_0'],data['arr_1'],data['arr_2'],data['arr_3']

st.write("TE过程的原始训练集维度",traindata_x.shape, traindata_y.shape)
st.write("TE过程的原始测试集维度",testdata_x.shape, testdata_y.shape)


st.info("求正常样本的均值和方差，并以此为基准对所有数据做标准化")
normal_samples=np.vstack((traindata_x[:500,:],testdata_x[:960,:]))
normal_labels=np.hstack((traindata_y[:500],testdata_y[:960]))


mean=np.mean(normal_samples,axis=0)
std=np.std(normal_samples,axis=0)

traindata_x2=(traindata_x-mean)/std
testdata_x2=(testdata_x-mean)/std

st.info("求每个类别标准化后的norm2，故障和正常数据的norm2有较大差异")
norm_0=np.mean(traindata_x2[:500,:]**2)

norm=[norm_0]
for i in range(1,22):
    norm_i=np.mean(traindata_x2[500+(i-1)*480:500+i*480,:]**2)
    norm.append(norm_i)

from matplotlib import pyplot as plt
fig = plt.figure(figsize=(12,4))
plt.plot(norm)
st.write(fig)

st.warning("！！！猜想：norm2大的类别对应的测试准确率要高一些，是否是正相关的？")

#训练集中的故障数据前填充20个零向量，使得训练集为(22, 500, 52)

traindata_x_pad=[traindata_x2[:500,:]]
traindata_y_pad=[traindata_y[:500]]
for i in range(1,22):
    data_i=traindata_x2[500+(i-1)*480:500+i*480,:]
    #print(data_i.shape)
    data_i=np.vstack((np.zeros((20,52)),data_i))
    #print(i,data_i.shape)
    label_i=traindata_y[500+(i-1)*480:500+i*480]
    label_i=np.hstack((np.zeros(20,dtype=np.int32),label_i))
    
    traindata_x_pad.append(data_i)
    traindata_y_pad.append(label_i)

traindata_x_pad=np.array(traindata_x_pad)
traindata_y_pad=np.array(traindata_y_pad)
traindata_y_pad=traindata_y_pad.reshape(traindata_y_pad.shape[0],traindata_y_pad.shape[1],-1)


dataset1=np.concatenate((traindata_x_pad,traindata_y_pad),axis=2)


testdata_x_pad=testdata_x2.reshape(22,-1,testdata_x2.shape[1])
testdata_y_pad=testdata_y.reshape(22,-1,1)
print(testdata_x_pad.shape,testdata_y_pad.shape)

dataset2=np.concatenate((testdata_x_pad,testdata_y_pad),axis=2)


def create_dataset(dataset, look_back=6):
    dataX, dataY = [],[]
    for j in range(dataset.shape[0]):
        for i in range(dataset.shape[1]-look_back):
            a = dataset[j,i:(i + look_back),0:-1]
            dataX.append(a)
            dataY.append(dataset[j,i:(i + look_back),-1])
    
    return np.array(dataX), np.array(dataY,dtype=np.int32)

# 创建好输入输出
train_X, train_Y = create_dataset(dataset1)
test_X, test_Y = create_dataset(dataset2)

st.write("处理后的训练集维度", train_X.shape,train_Y.shape,train_X.dtype,train_Y.dtype)
st.write("处理后的测试集维度", test_X.shape,test_Y.shape,test_X.dtype,test_Y.dtype)



data_all = np.concatenate((train_X,test_X),axis=0)
label_all = np.concatenate((train_Y,test_Y),axis=0)
st.write(data_all.shape,label_all.shape)


from sklearn.model_selection import train_test_split
st.info("重新划分训练集和测试集")
train_X,test_X,train_Y,test_Y=train_test_split(data_all, label_all, test_size=0.2, random_state=99) 
print(train_X.shape,test_X.shape,train_Y.shape,test_Y.shape)

#转换成Tensor
train_x = (torch.from_numpy(train_X)).float()
train_y = torch.from_numpy(train_Y).long()
test_x = (torch.from_numpy(test_X)).float()
test_y = torch.from_numpy(test_Y).long()


# 先转换成 torch 能识别的 Dataset
import torch.utils.data as Data

train_dataset = Data.TensorDataset(train_x,train_y)
# 把 dataset 放入 DataLoader
train_loader = Data.DataLoader(
    dataset=train_dataset,      # torch TensorDataset format
    batch_size=64,      # mini batch size
    shuffle=True,               # 要不要打乱数据 (打乱比较好)
    num_workers=1,              # 多线程来读数据
)
test_dataset = Data.TensorDataset(test_x,test_y)
# 把 dataset 放入 DataLoader
test_loader = Data.DataLoader(
    dataset=test_dataset,      # torch TensorDataset format
    batch_size=64,      # mini batch size
    #shuffle=True,               # 要不要打乱数据 (打乱比较好)
    num_workers=1,              # 多线程来读数据
)
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
st.info("内核类型",device)


with st.echo():
    st.write('''
        self.dropout = nn.Dropout(p=0.2)  #1/(1-p)
        self.encoder=nn.Sequential(OrderedDict([
                    ('sparse1',nn.Linear(self.input_size, self.input_size)),
                    ('action1',nn.Tanh()),
                    ('sparse2',nn.Linear(self.input_size, self.embedding_size)),
                    ('action2',nn.Tanh())
                    ]))
        self.decoder=nn.Sequential(OrderedDict([
                    ('fc1',nn.Linear(self.embedding_size, self.input_size)),
                    ('action3',nn.Tanh()),
                    ('fc2',nn.Linear(self.input_size, self.input_size))
                    ]))
        self.reg = nn.Linear(self.embedding_size, self.output_size)
    ''')

from collections import OrderedDict

class Sparse_autoencoder(nn.Module):
    def __init__(self, input_size=52, embedding_size=30, output_size=22, device=device):
        super(Sparse_autoencoder,self).__init__()
        self.input_size=input_size
        self.embedding_size=embedding_size
        self.output_size=output_size
        self.device=device
        
        self.dropout = nn.Dropout(p=0.2)  #1/(1-p)
        self.encoder=nn.Sequential(OrderedDict([
                    ('sparse1',nn.Linear(self.input_size, self.input_size)),
                    ('action1',nn.Tanh()),
                    ('sparse2',nn.Linear(self.input_size, self.embedding_size)),
                    ('action2',nn.Tanh())
                    ]))
        self.decoder=nn.Sequential(OrderedDict([
                    ('fc1',nn.Linear(self.embedding_size, self.input_size)),
                    ('action3',nn.Tanh()),
                    ('fc2',nn.Linear(self.input_size, self.input_size))
                    ]))
        self.reg = nn.Linear(self.embedding_size, self.output_size)
        
    def init_weights(self, initrange=0.2):
        """Initialize weights."""
        self.encoder.sparse1.weight.data.uniform_(-initrange, initrange)
        self.encoder.sparse1.bias.data.uniform_(-initrange, initrange)
        self.encoder.sparse2.weight.data.uniform_(-initrange, initrange)
        self.encoder.sparse2.bias.data.uniform_(-initrange, initrange) 
        self.decoder.fc1.weight.data.uniform_(-initrange, initrange)
        self.decoder.fc1.bias.data.uniform_(-initrange, initrange)
        self.decoder.fc2.weight.data.uniform_(-initrange, initrange)
        self.decoder.fc2.bias.data.uniform_(-initrange, initrange)
        self.reg.weight.data.uniform_(-initrange, initrange)
        self.reg.bias.data.uniform_(-initrange, initrange)
        
    def forward(self, x): 
        b, l, h = x.shape  #(batch, seq, hidden)
        x = x.contiguous().view(l*b,-1) 
        e = self.encoder(self.dropout(x))
        x_bar = self.decoder(e)
        #out = self.reg(self.dropout(e))
        out = self.reg(e)
        x_bar = x_bar.contiguous().view(b,l,-1)
        
        return x_bar,e,out
    
    def load_model(self, load_dir):
        if self.device.type == 'cuda':
            self.load_state_dict(torch.load(open(load_dir, 'rb')))
        else:
            self.load_state_dict(torch.load(open(load_dir, 'rb'), map_location=lambda storage, loc: storage))

    def save_model(self, save_dir):
        torch.save(self.state_dict(), open(save_dir, 'wb'))

st.stop()

Sparse_AE = Sparse_autoencoder(device=device)
Sparse_AE.to(device)
Loss_MSE = nn.MSELoss()
Loss_CE = nn.CrossEntropyLoss()
optimizer_SparseAE = torch.optim.SGD(Sparse_AE.parameters(), lr=1e-3,momentum=0.9)
              

#稀疏编码器加L1约束
def L1_penalty(param, debug=False):
    if isinstance(param, torch.Tensor):
        param= [param]
    total_L1_norm=0
    for p in filter(lambda p: p.data is not None, param):
        param_norm = p.data.norm(p=1) 
        if debug:print('param_norm',param_norm)
        total_L1_norm += param_norm
        if debug:print('L1',total_L1_norm)
        
    return total_L1_norm

test=torch.tensor([[[-1.0,-2.0],
                   [1.0,2.0]],
                   [[-1.0,-2.0],
                   [1.0,2.0]]])
print(test.shape)
print(L1_penalty(test,debug=True))

def val_AE(net,test_loader,lambd1,lambd2):
    Losses=[]
    Acces=[]
    Acc=[0]*22 
    Det=[0]*22
    Total=[0]*22
    #net.eval()
    with torch.no_grad():
        for step, (batch_x, batch_y) in enumerate(test_loader):
          #if step<3:
            batch_x=batch_x.to(device)
            batch_y=batch_y.to(device)
            batch_y=batch_y.view(-1)
            
            x_bar,embedding,out = net(batch_x)
            Loss_L1_penalty = lambd1 * L1_penalty(embedding)
            loss_L2 = Loss_MSE(x_bar,batch_x)            
            loss_CE = lambd2 * Loss_CE(out,batch_y)
            loss = loss_L2 + Loss_L1_penalty + loss_CE
            total = batch_y.size(0)
            Losses.append(loss.item()/total)
            
            out=F.softmax(out,1)
            _,index=out.max(dim=1)
            acc=(index==batch_y).sum().cpu().numpy() 
            Acces.append(acc/total)
            
              #按类别统计正确率
            for i in range(batch_y.shape[0]):
                Total[batch_y[i]]+=1
                if index[i]==batch_y[i]:
                    Acc[batch_y[i]]+=1
                if (index[i]>0)==(batch_y[i]>0):
                    Det[batch_y[i]]+=1
    for i in range(22):
        Acc[i]/=Total[i]
        Det[i]/=Total[i]
   
        #print(Losses)
    return np.mean(Losses),np.mean(Acces),Acc,Det



'''
print("classication_acc",allclass_acc[-1])
print("det_acc",alldet_acc[-1])
k=[1,2,4,5,6,7,8,10,11,12,13,14,16,17,18,19,20]
det=[]
for i in k:
    det.append(alldet_acc[i])
det_mean=np.mean(np.array(det))
print("mean",det_mean)

#迭代200次, lambd=1e-5
print(test_Acc[-1])
plt.plot(train_Loss[1:])
plt.plot(test_Loss)
plt.plot(train_Acc)
plt.plot(test_Acc)
plt.show()
'''

#Sparse_AE.save_model("SparseAE_nodropout_epoch200.pth")
 
Sparse_AE.load_model("SparseAE_epoch200.pth")

Loss,ACC = val_AE(Sparse_AE,test_loader,lambd1=1e-4, lambd2=100)   
print(Loss)
print(ACC)


print("csds")

test_seq_x,test_seq_y=test_dataset[100:120]
print(test_seq_y)
Embedding = Sparse_AE.encoder(test_seq_x.to(device))
print(Embedding.shape,Embedding[0,:,:])

print((Embedding==0).sum().float()/(20*6*200))





#定义模型
class lstm(nn.Module):
    def __init__(self, input_size=52, hidden_size=100, output_size=22, num_layers=3, batch_first=True, device=device):            
          super(lstm, self).__init__()
          self.input_size=input_size
          self.hidden_size=hidden_size
          self.output_size=output_size
          self.num_layers=num_layers
          self.batch_first=batch_first
          self.device=device
        
          self.dropout = nn.Dropout(p=0.2)  #1/(1-p)
          self.rnn = nn.LSTM(self.input_size, self.hidden_size, num_layers=self.num_layers, batch_first=self.batch_first)
          self.reg = nn.Linear(self.hidden_size, self.output_size)

    def init_weights(self, initrange=0.2):
        """Initialize weights."""
        for weight in self.rnn.parameters():
            weight.data.uniform_(-initrange, initrange)
        self.reg.weight.data.uniform_(-initrange, initrange)
        self.reg.bias.data.uniform_(-initrange, initrange)
        
    def init_hidden(self, input):
        minibatch_size = input.size(0) \
                if self.batch_first else input.size(1)
        h0 = torch.zeros(self.num_layers, minibatch_size, self.hidden_size, device=self.device)
        c0 = torch.zeros(self.num_layers, minibatch_size, self.hidden_size, device=self.device)
        return (h0, c0) 
    
    def forward(self, x):
         h0_c0 = self.init_hidden(x)
         out,ht_ct = self.rnn(self.dropout(x),None) 
         b, l, h = out.shape  #(batch, seq, hidden)
         #print(out.shape)
         out = out.contiguous().view(l*b, h) #转化为线性层的输入方式
         y = self.reg(self.dropout(out))
         #y = y.view(b, l, -1)        
         return y  
    
    def load_model(self, load_dir):
        if self.device.type == 'cuda':
            self.load_state_dict(torch.load(open(load_dir, 'rb')))
        else:
            self.load_state_dict(torch.load(open(load_dir, 'rb'), map_location=lambda storage, loc: storage))

    def save_model(self, save_dir):
        torch.save(self.state_dict(), open(save_dir, 'wb'))

    
net = lstm(device=device)
net.to(device)


criterion = nn.CrossEntropyLoss()

#稀疏编码器加L1约束
optimizer = torch.optim.Adam(net.parameters(), lr=1e-2)


def val_acc(net,test_loader):
    Losses=[]
    Acces=[] 
    Dets=[]
    #net.eval()
    with torch.no_grad():
        for step, (batch_x, batch_y) in enumerate(test_loader):
          #if step<3:
            batch_x=batch_x.to(device)
            batch_y=batch_y.to(device)
            out = net(batch_x)
            batch_y=batch_y.view(-1)
            loss = criterion(out,batch_y)
            total = batch_y.size(0)
            Losses.append(loss.item()/total)
            
            out=F.softmax(out,1)
            _,index=out.max(dim=1)
            #print(index.size(),index)
            #print('test_result:',np.unique(index.cpu().numpy()))
            
            acc=(index==batch_y).sum().cpu().numpy()       
            Acces.append(acc/total)
            det=((index>0)==(batch_y>0)).sum().cpu().numpy()       
            Dets.append(det/total)
        #print(Losses,Acces)
    return np.mean(Losses),np.mean(Acces),np.mean(Dets)

net.load_model("LSTM3_L10_epoch200.pth")
#batch_size=64
look_back=100
#训练完成之后，我们可以用训练好的模型去预测后面的结果
def jude(x):
    if x in (3,9,15):return True
    else: return False

Acc=[0]*22 
Det=[0]*22
Total=[0]*22
net = net.eval()
with torch.no_grad():
    for step, (batch_x, batch_y) in enumerate(test_loader):
        batch_x=batch_x.to(device)
        batch_y=batch_y.to(device)
        out = net(batch_x)
        batch_y=batch_y.view(-1)
        out=F.softmax(out,1)
        _,index=out.max(dim=1)
        
       # print('test_result:',np.unique(index.cpu().numpy()))
        index=index.cpu().numpy()
        #输出3，9，15的预测值和真实值
        ind=index.reshape(-1,look_back)
        #print(ind.shape)
        row=np.where(ind==15)[0] 
        print("********************************************************************")
        print(row.shape)
        #print("row=",row)
        #for i in row:
           # if (ind[i,:]!=batch_y.reshape(-1,look_back)[i,:]).any():
               # print(ind[i,:],batch_y.reshape(-1,look_back)[i,:])
        #print(ind.shape,ind[row,:])
        batch_y=batch_y.cpu().numpy()
        print("********************************************************************")
        #按类别统计正确率
        for i in range(batch_y.shape[0]):
            Total[batch_y[i]]+=1
            if index[i]==batch_y[i]:
                Acc[batch_y[i]]+=1
            if (index[i]>0)==(batch_y[i]>0):
                Det[batch_y[i]]+=1
                
for i in range(22):
    Acc[i]/=Total[i]
    Det[i]/=Total[i]

#print(sum(Total)/6,Total)
print(Acc)
print(Det)

fig = plt.figure(figsize=(12,8))
#fig.subsubplots_adjust(left=0.2, bottom=0.2, right=0.8, top=0.8，hspace=0.2, wspace=0.3)
sub1=plt.subplot(2,1,1)
sub2=plt.subplot(2,1,2)

sub1.plot(Acc)
sub1.set_title(u'classfication accuracy')
sub1.set_xticks(range(22))
sub1.grid(True)
sub2.plot(Det)
sub2.set_title(u'detection accuracy')
sub2.set_xticks(range(22))
sub2.grid(True)
plt.show()

import numpy as np
Acc1=np.array([0.9948960589298277, 0.9997762062483215, 0.9998750988800533, 0.9787325088792845, 0.9990940387751405,
               0.996909355821449, 1.0, 0.9989421882904843, 0.9900534901198002, 0.9820989143546441, 0.987306773909765,
               0.990609657276324, 0.9932675747612337, 0.9938020110957004, 0.998448543354594, 0.9714311668256347,
               0.9860397361712459, 0.9979317476732161, 0.990303648890023, 0.9907189754397341, 0.983900198086568,
               0.9908818920074085])
Det1=np.array([0.9948960589298277, 1.0, 0.9998750988800533, 0.9846805597158629, 0.999909403877514, 0.9983222217316438, 
               1.0, 0.9998620245596284, 0.9991158657884267, 0.9863932448733413, 0.9945540614134305, 0.9968063301396635,
               0.9995694379207766, 0.9965325936199723, 1.0, 0.9789253758459372, 0.9928377776878566, 0.9985719210124587,
               0.9965552436846135, 0.9924211720839751, 0.9886627049353057, 0.9923065963812508])
np.savez('Zclassfiction_acc_100.npz',Acc1)
np.savez('Zdetection_acc_100.npz',Det1)
#给不同类别加权
weights=[1/x for x in Acc]
SUM=sum(weights)
weights=[x/SUM for x in weights]
print(weights)